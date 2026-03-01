"""
Chairman / Trustee Routes — Command Tower dashboard pages.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models.user import UserRole
from utils.permissions import require_role

router = APIRouter(prefix="/chairman", tags=["Chairman"])
templates = Jinja2Templates(directory="templates")


@router.get("/dashboard", response_class=HTMLResponse)
@require_role(UserRole.CHAIRMAN)
async def chairman_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = request.state.user
    return templates.TemplateResponse("chairman/command_tower.html", {
        "request": request, "user": user, "active_page": "chairman_dashboard"
    })