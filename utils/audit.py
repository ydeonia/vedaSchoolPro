"""Audit Logger — Track every important action in the system"""
from models.prelaunch import AuditLog, AuditAction
import uuid, json


async def log_audit(db, branch_id=None, user=None, action: AuditAction = AuditAction.CREATE,
                     entity_type: str = "", entity_id: str = "",
                     description: str = "", details: dict = None, ip: str = ""):
    """Log an audit event. Call from any route."""
    entry = AuditLog(
        branch_id=uuid.UUID(str(branch_id)) if branch_id else None,
        user_id=uuid.UUID(user["id"]) if user and "id" in user else None,
        user_name=user.get("full_name", user.get("email", "")) if user else "",
        user_role=user.get("role", "") if user else "",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else "",
        description=description,
        details=json.dumps(details) if details else None,
        ip_address=ip,
    )
    db.add(entry)
    await db.flush()
    return entry
