from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.crud.finance import create_finance_record
from app.crud.place import touch_place
from app.crud.schedule import create_schedule
from app.crud.team import add_team_member, create_team, get_team_by_name, get_team_member
from app.crud.user import get_or_create_user_by_openid
from app.models.finance import FinanceRecord
from app.models.place import Place
from app.models.schedule import Schedule
from app.models.team import Team
from app.models.user import User


def _utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value).astimezone(dt.timezone.utc)


@dataclass
class DemoSeedStats:
    created_teams: int = 0
    updated_teams: int = 0
    created_memberships: int = 0
    created_schedules: int = 0
    created_finance_records: int = 0


DEMO_TEAM_SPECS = [
    {
        "name": "Badz乐队",
        "legacy_names": ["Badz涔愰槦"],
        "members": [
            {"openid": "demo-badz-azhe", "nickname": "阿哲", "role": "admin"},
            {"openid": "demo-badz-xiaoman", "nickname": "小满", "role": "member"},
            {"openid": "demo-badz-aqing", "nickname": "阿清", "role": "member"},
            {"openid": "demo-badz-lulu", "nickname": "露露", "role": "member"},
        ],
        "schedules": [
            {
                "title": "排练新歌《逆光》",
                "description": "统一主歌和副歌层次，重点磨第二遍合声。",
                "location": "坏姿排练室",
                "start": "2026-03-19T19:30:00+08:00",
                "end": "2026-03-19T22:00:00+08:00",
                "created_by": "demo-badz-azhe",
            },
            {
                "title": "排练后聚餐",
                "description": "边复盘边确认周末小场演出歌单和到场时间。",
                "location": "老街烧烤",
                "start": "2026-03-19T22:20:00+08:00",
                "end": "2026-03-19T23:30:00+08:00",
                "created_by": "demo-badz-xiaoman",
            },
            {
                "title": "周末 Livehouse 演出",
                "description": "提前半小时完成试音和返送检查。",
                "location": "南门 Livehouse",
                "start": "2026-03-28T18:30:00+08:00",
                "end": "2026-03-28T22:00:00+08:00",
                "created_by": "demo-badz-aqing",
            },
            {
                "title": "演出海报补拍",
                "description": "补几组现场宣传图，顺便确认五一合作档期。",
                "location": "江边步道",
                "start": "2026-04-03T16:00:00+08:00",
                "end": "2026-04-03T17:30:00+08:00",
                "created_by": "demo-badz-lulu",
            },
            {
                "title": "器材联调和彩排",
                "description": "重点测鼓组拾音、贝斯 DI 和主唱耳返。",
                "location": "北仓器材棚",
                "start": "2026-04-18T14:00:00+08:00",
                "end": "2026-04-18T18:00:00+08:00",
                "created_by": "demo-badz-aqing",
            },
            {
                "title": "五一营地演出",
                "description": "商演场次，演完后现场复盘结算。",
                "location": "海边营地音乐节",
                "start": "2026-05-02T18:00:00+08:00",
                "end": "2026-05-02T21:30:00+08:00",
                "created_by": "demo-badz-azhe",
            },
            {
                "title": "五月演出复盘会",
                "description": "核对票房、周边销售和下轮排练计划。",
                "location": "乐队共享空间",
                "start": "2026-05-03T14:00:00+08:00",
                "end": "2026-05-03T16:00:00+08:00",
                "created_by": "demo-badz-azhe",
            },
        ],
        "finance": [
            {
                "amount": "180.00",
                "type": "expense",
                "category": "排练室",
                "occurred_at": "2026-03-19T18:50:00+08:00",
                "location": "坏姿排练室",
                "note": "三小时排练室费用。",
                "created_by": "demo-badz-azhe",
            },
            {
                "amount": "126.00",
                "type": "expense",
                "category": "聚餐",
                "occurred_at": "2026-03-19T22:35:00+08:00",
                "location": "老街烧烤",
                "note": "排练后四人聚餐，由小满统一记账。",
                "created_by": "demo-badz-xiaoman",
            },
            {
                "amount": "240.00",
                "type": "expense",
                "category": "打车",
                "occurred_at": "2026-03-28T23:10:00+08:00",
                "location": "南门 Livehouse",
                "note": "演出结束后带器材回仓。",
                "created_by": "demo-badz-aqing",
            },
            {
                "amount": "4800.00",
                "type": "income",
                "category": "演出收入",
                "occurred_at": "2026-03-29T12:00:00+08:00",
                "location": "南门 Livehouse",
                "note": "周末小场结算款。",
                "created_by": "demo-badz-lulu",
            },
            {
                "amount": "860.00",
                "type": "expense",
                "category": "器材维护",
                "occurred_at": "2026-04-18T18:20:00+08:00",
                "location": "北仓器材棚",
                "note": "更换鼓皮、琴线和 DI 线材。",
                "created_by": "demo-badz-aqing",
            },
            {
                "amount": "520.00",
                "type": "expense",
                "category": "服装道具",
                "occurred_at": "2026-04-26T19:00:00+08:00",
                "location": "南城市集",
                "note": "五一场服装和舞台小道具采购。",
                "created_by": "demo-badz-lulu",
            },
            {
                "amount": "9600.00",
                "type": "income",
                "category": "商演收入",
                "occurred_at": "2026-05-02T21:40:00+08:00",
                "location": "海边营地音乐节",
                "note": "五一商演尾款。",
                "created_by": "demo-badz-azhe",
            },
            {
                "amount": "1380.00",
                "type": "income",
                "category": "周边收入",
                "occurred_at": "2026-05-02T22:00:00+08:00",
                "location": "海边营地音乐节",
                "note": "演出现场贴纸和 T 恤销售。",
                "created_by": "demo-badz-xiaoman",
            },
        ],
    },
    {
        "name": "teamhome开发",
        "legacy_names": ["teamhome寮€鍙?"],
        "members": [
            {"openid": "demo-teamhome-monke", "nickname": "元宝", "role": "admin"},
            {"openid": "demo-teamhome-ning", "nickname": "铜钱", "role": "member"},
            {"openid": "demo-teamhome-yue", "nickname": "屯屯", "role": "member"},
        ],
        "schedules": [
            {
                "title": "搭建前后端骨架",
                "description": "初始化 FastAPI、Alembic 和小程序基础结构。",
                "location": "远程协作",
                "start": "2026-03-19T20:00:00+08:00",
                "end": "2026-03-19T23:00:00+08:00",
                "created_by": "demo-teamhome-monke",
            },
            {
                "title": "协作流程补齐",
                "description": "补登录、团队切换和基础联调链路。",
                "location": "远程协作",
                "start": "2026-03-19T23:05:00+08:00",
                "end": "2026-03-19T23:45:00+08:00",
                "created_by": "demo-teamhome-ning",
            },
            {
                "title": "昵称引导上线",
                "description": "首登采集昵称，补齐后续记录人信息。",
                "location": "远程协作",
                "start": "2026-03-19T23:50:00+08:00",
                "end": "2026-03-20T00:20:00+08:00",
                "created_by": "demo-teamhome-ning",
            },
            {
                "title": "修复小程序构建",
                "description": "处理开发环境端口、代理和构建异常。",
                "location": "远程协作",
                "start": "2026-03-20T00:30:00+08:00",
                "end": "2026-03-20T02:00:00+08:00",
                "created_by": "demo-teamhome-yue",
            },
            {
                "title": "助手规划成型",
                "description": "明确查询流、写入流和确认机制。",
                "location": "远程协作",
                "start": "2026-03-21T09:00:00+08:00",
                "end": "2026-03-21T11:30:00+08:00",
                "created_by": "demo-teamhome-monke",
            },
            {
                "title": "多语言体系落地",
                "description": "页面文案开始统一走 i18n。",
                "location": "远程协作",
                "start": "2026-03-21T14:00:00+08:00",
                "end": "2026-03-21T16:30:00+08:00",
                "created_by": "demo-teamhome-yue",
            },
            {
                "title": "模型容灾接入",
                "description": "补模型 fallback 和切换保护。",
                "location": "远程协作",
                "start": "2026-03-21T16:40:00+08:00",
                "end": "2026-03-21T18:00:00+08:00",
                "created_by": "demo-teamhome-monke",
            },
            {
                "title": "助手交互收口",
                "description": "压缩追问链路，减少任务中断。",
                "location": "远程协作",
                "start": "2026-03-21T18:10:00+08:00",
                "end": "2026-03-21T19:20:00+08:00",
                "created_by": "demo-teamhome-ning",
            },
            {
                "title": "接入 LangGraph 调试",
                "description": "把 prepare、queue 和 commit 可视化。",
                "location": "远程协作",
                "start": "2026-03-22T12:00:00+08:00",
                "end": "2026-03-22T15:00:00+08:00",
                "created_by": "demo-teamhome-monke",
            },
            {
                "title": "导出能力上线",
                "description": "支持助手侧导出团队数据。",
                "location": "远程协作",
                "start": "2026-03-25T00:10:00+08:00",
                "end": "2026-03-25T01:20:00+08:00",
                "created_by": "demo-teamhome-ning",
            },
            {
                "title": "分析页初版完成",
                "description": "把时间线和收支汇总成可视看板。",
                "location": "远程协作",
                "start": "2026-03-25T01:30:00+08:00",
                "end": "2026-03-25T03:00:00+08:00",
                "created_by": "demo-teamhome-yue",
            },
            {
                "title": "生产域名收口",
                "description": "整理生产域名、回调地址和 HTTPS 配置。",
                "location": "远程协作",
                "start": "2026-03-25T20:00:00+08:00",
                "end": "2026-03-25T21:00:00+08:00",
                "created_by": "demo-teamhome-monke",
            },
            {
                "title": "团队安全加固",
                "description": "按生产标准收紧认证、调试入口和环境配置。",
                "location": "远程协作",
                "start": "2026-03-28T10:00:00+08:00",
                "end": "2026-03-28T15:00:00+08:00",
                "created_by": "demo-teamhome-yue",
            },
            {
                "title": "时间线页重构",
                "description": "把日程和收支统一到同一时间线模型。",
                "location": "远程协作",
                "start": "2026-03-28T20:00:00+08:00",
                "end": "2026-03-28T23:30:00+08:00",
                "created_by": "demo-teamhome-monke",
            },
            {
                "title": "备案通过正式上线",
                "description": "完成备案收口后切正式环境，发布生产版本。",
                "location": "远程协作",
                "start": "2026-03-30T10:00:00+08:00",
                "end": "2026-03-30T12:00:00+08:00",
                "created_by": "demo-teamhome-monke",
            },
            {
                "title": "修 bug",
                "description": "3月31日至4月2日集中修复上线后反馈的问题并做回归确认。",
                "location": "远程协作",
                "start": "2026-03-31T10:00:00+08:00",
                "end": "2026-04-02T19:00:00+08:00",
                "created_by": "demo-teamhome-ning",
            },
            {
                "title": "跨天日程 UI 优化",
                "description": "4月1日至4月2日优化跨天日程在时间线中的展示和交互。",
                "location": "远程协作",
                "start": "2026-04-01T10:00:00+08:00",
                "end": "2026-04-02T18:00:00+08:00",
                "created_by": "demo-teamhome-yue",
            },
        ],
        "finance": [
            {
                "amount": "68.00",
                "type": "expense",
                "category": "域名",
                "occurred_at": "2026-03-25T20:30:00+08:00",
                "location": "线上服务",
                "note": "生产域名首年购买。",
                "created_by": "demo-teamhome-monke",
            },
            {
                "amount": "320.00",
                "type": "expense",
                "category": "云服务",
                "occurred_at": "2026-03-26T09:00:00+08:00",
                "location": "线上服务",
                "note": "数据库和容器主机月费。",
                "created_by": "demo-teamhome-ning",
            },
            {
                "amount": "88.00",
                "type": "expense",
                "category": "审核费用",
                "occurred_at": "2026-03-27T11:30:00+08:00",
                "location": "微信开放平台",
                "note": "资质补传和审核材料处理。",
                "created_by": "demo-teamhome-yue",
            },
            {
                "amount": "148.00",
                "type": "expense",
                "category": "模型调用",
                "occurred_at": "2026-03-27T18:00:00+08:00",
                "location": "线上服务",
                "note": "助手编排联调阶段的模型消耗。",
                "created_by": "demo-teamhome-yue",
            },
            {
                "amount": "420.00",
                "type": "income",
                "category": "广告收入",
                "occurred_at": "2026-03-28T22:10:00+08:00",
                "location": "线上服务",
                "note": "内测投放返还的渠道激励。",
                "created_by": "demo-teamhome-monke",
            },
        ],
    },
]


def ensure_demo_data(db: Session, *, force: bool = False) -> DemoSeedStats:
    if not force and not get_settings().demo_seed_auto_enabled():
        return DemoSeedStats()

    stats = DemoSeedStats()
    for spec in DEMO_TEAM_SPECS:
        _ensure_demo_team(db, spec, stats)
    return stats


def _ensure_demo_team(db: Session, spec: dict, stats: DemoSeedStats) -> None:
    users = _ensure_users(db, spec["members"])
    team = _find_existing_demo_team(db, spec, users)
    owner = users[spec["members"][0]["openid"]]

    if not team:
        team = create_team(db, name=spec["name"], owner_id=owner.id, join_password=None, is_demo=True)
        stats.created_teams += 1
    else:
        team_changed = False
        if team.name != spec["name"]:
            team.name = spec["name"]
            team_changed = True
        if not team.is_demo:
            team.is_demo = True
            team_changed = True
        if team.join_password is not None:
            team.join_password = None
            team_changed = True
        if team.owner_id != owner.id:
            team.owner_id = owner.id
            team_changed = True
        if team_changed:
            db.add(team)
            db.commit()
            db.refresh(team)
            stats.updated_teams += 1

    for member_spec in spec["members"]:
        user = users[member_spec["openid"]]
        membership = get_team_member(db, team_id=team.id, user_id=user.id)
        if membership:
            continue
        add_team_member(db, team_id=team.id, user_id=user.id, role=member_spec["role"])
        stats.created_memberships += 1

    existing_schedules = _existing_schedule_keys(db, team.id)
    existing_places = _existing_place_names(db, team.id)
    for item in spec["schedules"]:
        created_by = users[item["created_by"]]
        key = (item["title"], _utc(item["start"]), _utc(item["end"]))
        if key in existing_schedules:
            continue
        create_schedule(
            db,
            team_id=team.id,
            title=item["title"],
            description=item["description"],
            location=item["location"],
            location_latitude=None,
            location_longitude=None,
            is_all_day=False,
            start_time=key[1],
            end_time=key[2],
            created_by=created_by.id,
        )
        _touch_place_if_missing(db, team.id, item["location"], existing_places)
        existing_schedules.add(key)
        stats.created_schedules += 1

    existing_finance = _existing_finance_keys(db, team.id)
    for item in spec["finance"]:
        created_by = users[item["created_by"]]
        occurred_at = _utc(item["occurred_at"])
        key = (Decimal(item["amount"]), item["type"], item["category"], occurred_at, item["note"])
        if key in existing_finance:
            continue
        create_finance_record(
            db,
            team_id=team.id,
            user_id=created_by.id,
            amount=key[0],
            record_type=item["type"],
            category=item["category"],
            occurred_at=occurred_at,
            location=item["location"],
            location_latitude=None,
            location_longitude=None,
            note=item["note"],
        )
        _touch_place_if_missing(db, team.id, item["location"], existing_places)
        existing_finance.add(key)
        stats.created_finance_records += 1


def _ensure_users(db: Session, members: list[dict]) -> dict[str, User]:
    users: dict[str, User] = {}
    for member_spec in members:
        user = get_or_create_user_by_openid(
            db,
            member_spec["openid"],
            nickname=member_spec["nickname"],
            language="zh-CN",
        )
        users[member_spec["openid"]] = user
    return users


def _find_existing_demo_team(db: Session, spec: dict, users: dict[str, User]) -> Team | None:
    candidate_names = [spec["name"], *spec.get("legacy_names", [])]
    for name in candidate_names:
        team = get_team_by_name(db, name=name)
        if team and team.is_demo:
            return team

    owner_id = users[spec["members"][0]["openid"]].id
    member_ids = {users[item["openid"]].id for item in spec["members"]}
    demo_teams = db.query(Team).options(joinedload(Team.members)).filter(Team.is_demo.is_(True)).all()
    for team in demo_teams:
        team_member_ids = {member.user_id for member in team.members}
        if team.owner_id == owner_id:
            return team
        if member_ids and team_member_ids == member_ids:
            return team
    return None


def _existing_schedule_keys(db: Session, team_id) -> set[tuple[str, dt.datetime, dt.datetime]]:
    items = db.query(Schedule).filter(Schedule.team_id == team_id).all()
    return {(item.title, item.start_time, item.end_time) for item in items}


def _existing_finance_keys(db: Session, team_id) -> set[tuple[Decimal, str, str, dt.datetime, str | None]]:
    items = db.query(FinanceRecord).filter(FinanceRecord.team_id == team_id).all()
    return {(item.amount, item.type, item.category, item.occurred_at, item.note) for item in items}


def _existing_place_names(db: Session, team_id) -> set[str]:
    items = db.query(Place).filter(Place.team_id == team_id).all()
    return {item.name for item in items if item.name}


def _touch_place_if_missing(db: Session, team_id, name: str, existing_places: set[str]) -> None:
    normalized = (name or "").strip()
    if not normalized or normalized in existing_places:
        return
    touch_place(db, team_id=team_id, name=normalized)
    existing_places.add(normalized)
