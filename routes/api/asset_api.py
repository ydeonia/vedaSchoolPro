"""Asset / Inventory Management API"""
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models.user import UserRole
from utils.permissions import require_role
from utils.audit import log_audit, AuditAction
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import date, datetime

router = APIRouter(prefix="/api/school/assets")


# ─── Pydantic Schemas ────────────────────────────────────

class AssetCreateData(BaseModel):
    name: str
    category_id: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    quantity: Optional[int] = 1
    unit_price: Optional[float] = None
    purchase_date: Optional[str] = None
    warranty_expiry: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_contact: Optional[str] = None
    condition: Optional[str] = "good"
    assigned_to: Optional[str] = None
    serial_number: Optional[str] = None
    notes: Optional[str] = None


class AssetUpdateData(BaseModel):
    name: Optional[str] = None
    category_id: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[float] = None
    purchase_date: Optional[str] = None
    warranty_expiry: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_contact: Optional[str] = None
    condition: Optional[str] = None
    assigned_to: Optional[str] = None
    serial_number: Optional[str] = None
    notes: Optional[str] = None


class AssetLogData(BaseModel):
    log_type: str  # purchase, transfer, maintenance, repair, dispose, audit, damage
    description: str
    performed_by: Optional[str] = None
    log_date: Optional[str] = None
    cost: Optional[float] = None


class CategoryCreateData(BaseModel):
    name: str
    description: Optional[str] = None


# ─── SUMMARY ─────────────────────────────────────────────

@router.get("/summary")
@require_role(UserRole.SCHOOL_ADMIN)
async def asset_summary(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.asset import Asset, AssetCategory

    # Total count & value
    total = await db.scalar(
        select(func.count()).select_from(Asset).where(Asset.branch_id == branch_id, Asset.is_active == True)
    ) or 0
    total_value = await db.scalar(
        select(func.coalesce(func.sum(Asset.total_value), 0)).where(Asset.branch_id == branch_id, Asset.is_active == True)
    ) or 0

    # By condition
    cond_rows = (await db.execute(
        select(Asset.condition, func.count()).where(Asset.branch_id == branch_id, Asset.is_active == True)
        .group_by(Asset.condition)
    )).all()
    by_condition = {r[0]: r[1] for r in cond_rows}

    # By category
    cat_rows = (await db.execute(
        select(AssetCategory.name, func.count(Asset.id))
        .outerjoin(Asset, (Asset.category_id == AssetCategory.id) & (Asset.is_active == True))
        .where(AssetCategory.branch_id == branch_id, AssetCategory.is_active == True)
        .group_by(AssetCategory.name)
    )).all()
    by_category = {r[0]: r[1] for r in cat_rows}

    return {
        "total": total,
        "total_value": float(total_value),
        "by_condition": by_condition,
        "by_category": by_category,
    }


# ─── LIST ASSETS ─────────────────────────────────────────

@router.get("/list")
@require_role(UserRole.SCHOOL_ADMIN)
async def list_assets(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.asset import Asset, AssetCategory
    from sqlalchemy.orm import selectinload

    params = request.query_params
    category = params.get("category", "")
    condition = params.get("condition", "")
    search = params.get("search", "")

    q = select(Asset).where(Asset.branch_id == branch_id, Asset.is_active == True).options(selectinload(Asset.category))
    if category:
        q = q.where(Asset.category_id == uuid.UUID(category))
    if condition:
        q = q.where(Asset.condition == condition)
    if search:
        q = q.where(Asset.name.ilike(f"%{search}%"))
    q = q.order_by(Asset.created_at.desc())

    rows = (await db.execute(q)).scalars().all()
    assets = []
    for a in rows:
        assets.append({
            "id": str(a.id),
            "asset_code": a.asset_code,
            "name": a.name,
            "description": a.description,
            "category_id": str(a.category_id) if a.category_id else None,
            "category_name": a.category.name if a.category else "Uncategorized",
            "location": a.location,
            "quantity": a.quantity,
            "unit_price": float(a.unit_price) if a.unit_price else 0,
            "total_value": float(a.total_value) if a.total_value else 0,
            "purchase_date": a.purchase_date.isoformat() if a.purchase_date else None,
            "warranty_expiry": a.warranty_expiry.isoformat() if a.warranty_expiry else None,
            "vendor_name": a.vendor_name,
            "vendor_contact": a.vendor_contact,
            "condition": a.condition,
            "assigned_to": a.assigned_to,
            "serial_number": a.serial_number,
            "notes": a.notes,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })
    return {"assets": assets}


# ─── CREATE ASSET ────────────────────────────────────────

@router.post("/create")
@require_role(UserRole.SCHOOL_ADMIN)
async def create_asset(data: AssetCreateData, request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.asset import Asset

    # Auto-generate asset code: AST-XXXXXX
    code = f"AST-{str(uuid.uuid4())[:6].upper()}"

    asset = Asset(
        branch_id=branch_id,
        asset_code=code,
        name=data.name,
        description=data.description,
        location=data.location,
        quantity=data.quantity or 1,
        unit_price=data.unit_price,
        total_value=(data.unit_price or 0) * (data.quantity or 1),
        vendor_name=data.vendor_name,
        vendor_contact=data.vendor_contact,
        condition=data.condition or "good",
        assigned_to=data.assigned_to,
        serial_number=data.serial_number,
        notes=data.notes,
    )
    if data.category_id:
        asset.category_id = uuid.UUID(data.category_id)
    if data.purchase_date:
        try: asset.purchase_date = date.fromisoformat(data.purchase_date)
        except: pass
    if data.warranty_expiry:
        try: asset.warranty_expiry = date.fromisoformat(data.warranty_expiry)
        except: pass

    db.add(asset)
    await log_audit(db, user["branch_id"], user, AuditAction.CREATE, "asset", str(asset.id),
                    f"Created asset: {data.name} ({code})")
    await db.commit()
    return {"id": str(asset.id), "asset_code": code, "message": "Asset created"}


# ─── UPDATE ASSET ────────────────────────────────────────

@router.put("/{asset_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def update_asset(asset_id: str, data: AssetUpdateData, request: Request, db: AsyncSession = Depends(get_db)):
    from models.asset import Asset
    asset = (await db.execute(select(Asset).where(Asset.id == uuid.UUID(asset_id)))).scalar_one_or_none()
    if not asset: raise HTTPException(404, "Asset not found")

    for field in ["name", "description", "location", "vendor_name", "vendor_contact",
                  "condition", "assigned_to", "serial_number", "notes"]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(asset, field, val)

    if data.category_id is not None:
        asset.category_id = uuid.UUID(data.category_id) if data.category_id else None
    if data.quantity is not None:
        asset.quantity = data.quantity
    if data.unit_price is not None:
        asset.unit_price = data.unit_price
    # Recalculate total value
    asset.total_value = (float(asset.unit_price) if asset.unit_price else 0) * (asset.quantity or 1)
    if data.purchase_date:
        try: asset.purchase_date = date.fromisoformat(data.purchase_date)
        except: pass
    if data.warranty_expiry:
        try: asset.warranty_expiry = date.fromisoformat(data.warranty_expiry)
        except: pass

    asset.updated_at = datetime.utcnow()
    await db.commit()
    return {"id": str(asset.id), "message": "Asset updated"}


# ─── DELETE ASSET (soft) ─────────────────────────────────

@router.delete("/{asset_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def delete_asset(asset_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.asset import Asset
    asset = (await db.execute(select(Asset).where(Asset.id == uuid.UUID(asset_id)))).scalar_one_or_none()
    if not asset: raise HTTPException(404, "Asset not found")
    asset.is_active = False
    user = request.state.user
    await log_audit(db, user["branch_id"], user, AuditAction.DELETE, "asset", str(asset.id),
                    f"Soft-deleted asset: {asset.name}")
    await db.commit()
    return {"message": f"Asset '{asset.name}' deleted"}


# ─── ADD LOG ENTRY ───────────────────────────────────────

@router.post("/{asset_id}/log")
@require_role(UserRole.SCHOOL_ADMIN)
async def add_asset_log(asset_id: str, data: AssetLogData, request: Request, db: AsyncSession = Depends(get_db)):
    from models.asset import Asset, AssetLog
    asset = (await db.execute(select(Asset).where(Asset.id == uuid.UUID(asset_id)))).scalar_one_or_none()
    if not asset: raise HTTPException(404, "Asset not found")

    log = AssetLog(
        asset_id=asset.id,
        log_type=data.log_type,
        description=data.description,
        performed_by=data.performed_by,
        cost=data.cost,
    )
    if data.log_date:
        try: log.log_date = date.fromisoformat(data.log_date)
        except: pass

    db.add(log)

    # If log is dispose, update condition
    if data.log_type == "dispose":
        asset.condition = "disposed"
    elif data.log_type == "damage":
        asset.condition = "damaged"
    asset.updated_at = datetime.utcnow()

    await db.commit()
    return {"id": str(log.id), "message": "Log entry added"}


# ─── GET LOGS FOR ASSET ──────────────────────────────────

@router.get("/{asset_id}/logs")
@require_role(UserRole.SCHOOL_ADMIN)
async def get_asset_logs(asset_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.asset import AssetLog
    rows = (await db.execute(
        select(AssetLog).where(AssetLog.asset_id == uuid.UUID(asset_id))
        .order_by(AssetLog.log_date.desc(), AssetLog.created_at.desc())
    )).scalars().all()
    logs = []
    for l in rows:
        logs.append({
            "id": str(l.id),
            "log_type": l.log_type,
            "description": l.description,
            "performed_by": l.performed_by,
            "log_date": l.log_date.isoformat() if l.log_date else None,
            "cost": float(l.cost) if l.cost else 0,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        })
    return {"logs": logs}


# ─── CREATE CATEGORY ─────────────────────────────────────

@router.post("/categories/create")
@require_role(UserRole.SCHOOL_ADMIN)
async def create_category(data: CategoryCreateData, request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.asset import AssetCategory
    cat = AssetCategory(
        branch_id=branch_id,
        name=data.name,
        description=data.description,
    )
    db.add(cat)
    await db.commit()
    return {"id": str(cat.id), "message": f"Category '{data.name}' created"}


# ─── LIST CATEGORIES ─────────────────────────────────────

@router.get("/categories")
@require_role(UserRole.SCHOOL_ADMIN)
async def list_categories(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    branch_id = uuid.UUID(user["branch_id"])
    from models.asset import AssetCategory
    rows = (await db.execute(
        select(AssetCategory).where(AssetCategory.branch_id == branch_id, AssetCategory.is_active == True)
        .order_by(AssetCategory.name)
    )).scalars().all()
    categories = [{"id": str(c.id), "name": c.name, "description": c.description} for c in rows]
    return {"categories": categories}


# ─── DELETE CATEGORY (soft) ──────────────────────────────

@router.delete("/categories/{cat_id}")
@require_role(UserRole.SCHOOL_ADMIN)
async def delete_category(cat_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    from models.asset import AssetCategory
    cat = (await db.execute(select(AssetCategory).where(AssetCategory.id == uuid.UUID(cat_id)))).scalar_one_or_none()
    if not cat: raise HTTPException(404, "Category not found")
    cat.is_active = False
    await db.commit()
    return {"message": f"Category '{cat.name}' deleted"}
