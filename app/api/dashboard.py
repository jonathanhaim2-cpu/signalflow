from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.core.deps import get_current_user_optional
from app.core.templates import templates
from app.models.user import User

router = APIRouter(tags=["dashboard"])


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
        {"nav_mode": "auth", "auth_alt": "login"},
    )


@router.get("/login")
async def login_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"nav_mode": "auth", "auth_alt": "signup"},
    )


@router.get("/guides")
async def guides_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        request,
        "guides.html",
        {"nav_mode": "app" if user else "marketing", "user": user},
    )


def _legal_context(user: User | None, page: str) -> dict:
    return {
        "nav_mode": "app" if user else "marketing",
        "user": user,
        "legal_current": page,
    }


@router.get("/pricing")
async def pricing_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    return templates.TemplateResponse(request, "pricing.html", _legal_context(user, "pricing"))


@router.get("/terms")
async def terms_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    return templates.TemplateResponse(request, "terms.html", _legal_context(user, "terms"))


@router.get("/privacy")
async def privacy_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    return templates.TemplateResponse(request, "privacy.html", _legal_context(user, "privacy"))


@router.get("/refunds")
async def refunds_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    return templates.TemplateResponse(request, "refunds.html", _legal_context(user, "refunds"))


@router.api_route("/dashboard", methods=["GET", "POST"])
async def dashboard_page(request: Request, user: User | None = Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse(url="/login")
    if request.method == "POST":
        checkout = request.query_params.get("checkout") or "success"
        return RedirectResponse(url=f"/dashboard?checkout={checkout}", status_code=303)
    return templates.TemplateResponse(request, "dashboard.html", {"user": user, "nav_mode": "app"})
