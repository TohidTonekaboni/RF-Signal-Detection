from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User


def audit(db: AsyncSession, actor: User | str | None, action: str, entity: str | None = None,
          entity_id: object | None = None, detail: dict | None = None) -> None:
    """Add an audit row to the current transaction (the caller commits)."""
    name = actor.username if isinstance(actor, User) else (actor or "system")
    db.add(AuditLog(user_id=actor.id if isinstance(actor, User) else None, actor=name, action=action,
                    entity=entity, entity_id=str(entity_id) if entity_id is not None else None, detail=detail))
