import uuid

from sqlalchemy.orm import Session

from app.models.place import Place


def list_places(db: Session, *, team_id: uuid.UUID, query: str | None = None, limit: int = 20) -> list[Place]:
    stmt = db.query(Place).filter(Place.team_id == team_id)
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.filter(Place.name.ilike(like))
    return stmt.order_by(Place.use_count.desc(), Place.created_at.desc()).limit(limit).all()


def get_place_by_name(db: Session, *, team_id: uuid.UUID, name: str) -> Place | None:
    normalized = name.strip()
    return db.query(Place).filter(Place.team_id == team_id, Place.name == normalized).first()


def touch_place(db: Session, *, team_id: uuid.UUID, name: str) -> Place | None:
    normalized = (name or "").strip()
    if not normalized:
        return None
    place = get_place_by_name(db, team_id=team_id, name=normalized)
    if place:
      place.use_count += 1
      db.add(place)
      db.commit()
      db.refresh(place)
      return place

    place = Place(team_id=team_id, name=normalized, use_count=1)
    db.add(place)
    db.commit()
    db.refresh(place)
    return place
