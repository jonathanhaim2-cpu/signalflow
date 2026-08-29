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
    return templates.TemplateResponse(request, "landing.html", {"nav_mode": "marketing"})


@router.get("/signup")
async def signup_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request,
        "signup.html",
        {"nav_mode": "auth", "auth_alt": "login", "auth_alt_label": "כניסה"},
    )


@router.get("/login")
async def login_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"nav_mode": "auth", "auth_alt": "signup", "auth_alt_label": "הרשמה"},
    )


@router.get("/guides")
async def guides_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        request,
        "guides.html",
        {"nav_mode": "app" if user else "marketing", "user": user},
    )


@router.get("/dashboard")
async def dashboard_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "dashboard.html", {"user": user, "nav_mode": "app"})
