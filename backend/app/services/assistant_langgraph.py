from __future__ import annotations

import uuid

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_LANGGRAPH_BASE_URL_CACHE: str | None = None
_LANGGRAPH_FALLBACK_URLS = (
    "http://langgraph:22024",
    "http://127.0.0.1:22024",
    "http://localhost:22024",
)
_LANGGRAPH_THREAD_NAMESPACE = uuid.UUID("2f6b44cd-9cf9-4027-9c73-bca142f2d128")
_GRAPH_SESSION_FACTORIES: dict[str, sessionmaker] = {}


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def empty_graph_state(*, thread_id: str = "") -> dict:
    return {
        "available": False,
        "thread_id": thread_id,
        "thread_status": "",
        "highlighted_stages": [],
        "active_stage": "",
        "next_nodes": [],
        "updated_at": "",
    }


def get_assistant_id() -> str:
    configured = _normalize_optional_text(get_settings().LANGGRAPH_ASSISTANT_ID)
    return configured or "assistant_orchestrator"


def new_graph_db_session() -> Session:
    database_url = get_settings().DATABASE_URL
    factory = _GRAPH_SESSION_FACTORIES.get(database_url)
    if factory is None:
        engine = create_engine(database_url, pool_pre_ping=True)
        factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        _GRAPH_SESSION_FACTORIES[database_url] = factory
    return factory()


def _langgraph_base_urls() -> list[str]:
    global _LANGGRAPH_BASE_URL_CACHE
    settings = get_settings()
    configured = _normalize_optional_text(settings.LANGGRAPH_API_URL)
    ordered: list[str] = []
    if _LANGGRAPH_BASE_URL_CACHE:
        ordered.append(_LANGGRAPH_BASE_URL_CACHE.rstrip("/"))
    if configured:
        ordered.append(configured.rstrip("/"))
    ordered.extend(_LANGGRAPH_FALLBACK_URLS)
    deduped: list[str] = []
    for url in ordered:
        normalized = (url or "").strip().rstrip("/")
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def resolve_thread_id(session_id: str | None) -> str:
    token = _normalize_optional_text(session_id)
    if not token:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(token))
    except ValueError:
        return str(uuid.uuid5(_LANGGRAPH_THREAD_NAMESPACE, token))


def _langgraph_request_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    api_key = _normalize_optional_text(get_settings().LANGSMITH_API_KEY)
    if api_key:
        headers["X-Api-Key"] = api_key
    return headers


def request_json(method: str, path: str, payload: dict | None = None) -> dict:
    global _LANGGRAPH_BASE_URL_CACHE
    settings = get_settings()
    timeout = max(float(settings.LANGGRAPH_REQUEST_TIMEOUT_SECONDS or 45), 5.0)
    last_error: Exception | None = None
    candidates = _langgraph_base_urls()
    for index, base_url in enumerate(candidates):
        url = f"{base_url}{path}"
        try:
            with httpx.Client(timeout=timeout, headers=_langgraph_request_headers()) as client:
                request_kwargs = {"json": payload} if payload is not None else {}
                response = client.request(method.upper(), url, **request_kwargs)
            response.raise_for_status()
            _LANGGRAPH_BASE_URL_CACHE = base_url
            if not response.content:
                return {}
            data = response.json()
            return data if isinstance(data, dict) else {"output": data}
        except httpx.RequestError as exc:
            last_error = exc
            continue
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()
            message = f"LangGraph API request failed: {exc.response.status_code} {detail[:240]}".strip()
            last_error = RuntimeError(message)
            should_try_next = exc.response.status_code in {404, 502, 503, 504} and index < len(candidates) - 1
            if should_try_next:
                continue
            raise last_error from exc
    raise RuntimeError(f"LangGraph API unavailable: {last_error}") from last_error


def post_json(path: str, payload: dict) -> dict:
    return request_json("POST", path, payload)


def get_json(path: str) -> dict:
    return request_json("GET", path)


def ensure_thread(*, thread_id: str, team_id: uuid.UUID, user_id: uuid.UUID, locale: str) -> None:
    post_json(
        "/threads",
        {
            "thread_id": thread_id,
            "if_exists": "do_nothing",
            "metadata": {
                "team_id": str(team_id),
                "user_id": str(user_id),
                "locale": locale,
                "source": "teamhome-api",
            },
        },
    )


def extract_langgraph_response(payload: dict) -> dict:
    response = payload.get("response") if isinstance(payload, dict) else None
    if isinstance(response, dict):
        return response
    error = payload.get("__error__") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = _normalize_optional_text(error.get("message")) or _normalize_optional_text(error.get("error")) or "unknown error"
        raise RuntimeError(f"LangGraph run failed: {message}")
    raise RuntimeError("LangGraph run output missing response payload")


def collect_state_nodes(snapshot: object) -> list[str]:
    collected: list[str] = []

    def append_node(value: object) -> None:
        text = _normalize_optional_text(value)
        if text:
            collected.append(text)

    def walk(state: object) -> None:
        if not isinstance(state, dict):
            return
        for item in state.get("next") or []:
            append_node(item)
        metadata = state.get("metadata")
        if isinstance(metadata, dict):
            writes = metadata.get("writes")
            if isinstance(writes, dict):
                for key in writes.keys():
                    append_node(key)
        tasks = state.get("tasks")
        if isinstance(tasks, list):
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                append_node(task.get("name"))
                interrupts = task.get("interrupts")
                if isinstance(interrupts, list):
                    for interrupt in interrupts:
                        if isinstance(interrupt, dict):
                            append_node(interrupt.get("node"))
                walk(task.get("state"))

    walk(snapshot)
    return collected


def collect_response_payloads(snapshot: object) -> list[dict]:
    collected: list[dict] = []

    def walk(state: object) -> None:
        if isinstance(state, dict):
            response = state.get("response")
            if isinstance(response, dict):
                collected.append(response)
            if "intent" in state or "status" in state:
                collected.append(state)
            for value in state.values():
                if isinstance(value, (dict, list)):
                    walk(value)
            return
        if isinstance(state, list):
            for item in state:
                if isinstance(item, (dict, list)):
                    walk(item)

    walk(snapshot)
    return collected


def map_nodes_to_stages(node_names: list[str], *, stage_map: dict[str, str], stage_order: tuple[str, ...]) -> list[str]:
    mapped: list[str] = []
    for node_name in node_names:
        stage = stage_map.get(node_name)
        if stage and stage not in mapped:
            mapped.append(stage)
    return [stage for stage in stage_order if stage in mapped]


def normalize_highlighted_stages(stages: list[str], *, stage_order: tuple[str, ...]) -> list[str]:
    present = {stage for stage in stages if stage in stage_order}
    if not present:
        return []
    present.add("prepare")
    if present - {"prepare"}:
        present.add("loop_guard")
    return [stage for stage in stage_order if stage in present]


def resolve_active_stage(
    *,
    next_nodes: list[str],
    raw_nodes: list[str],
    highlighted_stages: list[str],
    stage_map: dict[str, str],
    stage_order: tuple[str, ...],
) -> str:
    next_stages = map_nodes_to_stages(next_nodes, stage_map=stage_map, stage_order=stage_order)
    if next_stages:
        return next_stages[-1]

    mapped_raw = map_nodes_to_stages(raw_nodes, stage_map=stage_map, stage_order=stage_order)
    if mapped_raw:
        return mapped_raw[-1]

    if highlighted_stages:
        return highlighted_stages[-1]

    return ""


def graph_stage_fallback_from_response(
    response: dict,
    *,
    query_finance_intent: str,
    create_finance_intent: str,
    query_schedule_intent: str,
    create_schedule_intent: str,
    mutating_intents: set[str],
    collecting_status: str,
    executed_status: str,
    unsupported_status: str,
    cancelled_status: str,
    stage_order: tuple[str, ...],
) -> list[str]:
    payload = response if isinstance(response, dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    status = _normalize_optional_text(payload.get("status")) or ""
    result_items = data.get("results") if isinstance(data.get("results"), list) else []
    intents: list[str] = []
    for item in result_items:
        if isinstance(item, dict):
            intent = _normalize_optional_text(item.get("intent"))
            if intent:
                intents.append(intent)
    direct_intent = _normalize_optional_text(payload.get("intent"))
    if direct_intent:
        intents.append(direct_intent)

    stages: list[str] = []
    if any(intent in {query_finance_intent, create_finance_intent} for intent in intents):
        stages.append("expense_subgraph")
    if any(intent in {query_schedule_intent, create_schedule_intent} for intent in intents):
        stages.append("schedule_subgraph")
    if stages or status in {collecting_status, executed_status, unsupported_status, cancelled_status, "blocked", "awaiting_confirmation", "collecting_conflict_update"}:
        stages.append("collect_result")
    if status == executed_status and any(intent in mutating_intents for intent in intents):
        stages.append("commit_batch")
    return normalize_highlighted_stages(stages, stage_order=stage_order)


def build_visual_state(
    *,
    thread_id: str,
    thread: dict | None,
    state: dict | None,
    stage_map: dict[str, str],
    stage_order: tuple[str, ...],
    fallback_stages_fn=None,
) -> dict:
    thread_payload = thread if isinstance(thread, dict) else {}
    state_payload = state if isinstance(state, dict) else {}
    history_payload = []
    raw_nodes = collect_state_nodes(state_payload)
    if isinstance(state_payload.get("history"), list):
        history_payload = state_payload.get("history") or []
    for item in history_payload:
        raw_nodes.extend(collect_state_nodes(item))
    next_nodes = [item for item in state_payload.get("next") or [] if _normalize_optional_text(item)]
    highlighted_stages = normalize_highlighted_stages(
        map_nodes_to_stages(raw_nodes, stage_map=stage_map, stage_order=stage_order),
        stage_order=stage_order,
    )
    fallback_stages: list[str] = []
    if fallback_stages_fn and (not highlighted_stages or highlighted_stages == ["prepare"]):
        response_payloads = collect_response_payloads(state_payload)
        for payload in reversed(response_payloads):
            stages = fallback_stages_fn(payload)
            if stages and stages != ["prepare"]:
                fallback_stages = stages
                break
        if fallback_stages:
            highlighted_stages = fallback_stages
    active_stage = resolve_active_stage(
        next_nodes=next_nodes,
        raw_nodes=raw_nodes,
        highlighted_stages=highlighted_stages,
        stage_map=stage_map,
        stage_order=stage_order,
    )
    if fallback_stages and active_stage == "prepare":
        active_stage = fallback_stages[-1]
    return {
        "available": True,
        "thread_id": thread_id,
        "thread_status": _normalize_optional_text(thread_payload.get("status")) or "",
        "highlighted_stages": highlighted_stages,
        "active_stage": active_stage,
        "next_nodes": next_nodes,
        "updated_at": _normalize_optional_text(thread_payload.get("updated_at"))
        or _normalize_optional_text(state_payload.get("created_at"))
        or "",
    }


def get_history_states(thread_id: str, *, post_json_fn, limit: int = 24) -> list[dict]:
    payload = post_json_fn(f"/threads/{thread_id}/history", {"limit": max(1, min(limit, 100))})
    if isinstance(payload, dict):
        output = payload.get("output")
        if isinstance(output, list):
            return [item for item in output if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def get_visual_state(thread_id: str, *, get_json_fn, post_json_fn, stage_map: dict[str, str], stage_order: tuple[str, ...], fallback_stages_fn=None) -> dict:
    thread = get_json_fn(f"/threads/{thread_id}")
    state = get_json_fn(f"/threads/{thread_id}/state")
    state_payload = dict(state) if isinstance(state, dict) else {}
    state_payload["history"] = get_history_states(thread_id, post_json_fn=post_json_fn)
    return build_visual_state(
        thread_id=thread_id,
        thread=thread,
        state=state_payload,
        stage_map=stage_map,
        stage_order=stage_order,
        fallback_stages_fn=fallback_stages_fn,
    )


def attach_visual_state(response: dict, *, thread_id: str, get_visual_state_fn, fallback_stages_fn) -> dict:
    try:
        graph_state = get_visual_state_fn(thread_id)
    except Exception:
        graph_state = empty_graph_state(thread_id=thread_id)
    highlighted_stages = graph_state.get("highlighted_stages") or []
    if not highlighted_stages or highlighted_stages == ["prepare"]:
        fallback_stages = fallback_stages_fn(response)
        if fallback_stages:
            graph_state["highlighted_stages"] = fallback_stages
            highlighted_stages = fallback_stages
    if not graph_state.get("active_stage") and graph_state.get("highlighted_stages"):
        graph_state["active_stage"] = graph_state["highlighted_stages"][-1]
    elif graph_state.get("active_stage") == "prepare" and highlighted_stages and highlighted_stages != ["prepare"]:
        graph_state["active_stage"] = highlighted_stages[-1]
    data = dict(response.get("data") or {})
    data["graph_state"] = graph_state
    response["data"] = data
    return response


def fetch_graph_state(session_id: str | None, *, resolve_thread_id_fn, get_visual_state_fn) -> dict:
    token = _normalize_optional_text(session_id)
    if not token:
        return empty_graph_state()

    thread_id = resolve_thread_id_fn(token)
    try:
        return get_visual_state_fn(thread_id)
    except Exception:
        return empty_graph_state(thread_id=thread_id)
