from __future__ import annotations

from app.services.assistant_orchestrator import _get_assistant_graph


graph = _get_assistant_graph()
if graph is None:
    raise RuntimeError("LangGraph graph unavailable. Ensure langgraph is installed correctly.")
