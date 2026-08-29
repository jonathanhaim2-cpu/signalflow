from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.deps import get_current_user_optional
from app.models.user import User

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def index(request: Request, user: User | None = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "landing.html", {})


@router.get("/signup")
async def signup_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "signup.html", {})


@router.get("/login")
async def login_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "login.html", {})


@router.get("/dashboard")
async def dashboard_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "dashboard.html", {"user": user})
