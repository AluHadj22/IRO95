from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(tags=["Public"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    categories = db.query(models.Category).filter(models.Category.is_active == True).limit(6).all()
    courses = db.query(models.Course).filter(models.Course.is_active == True).order_by(models.Course.created_at.desc()).limit(6).all()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "categories": categories,
        "courses": courses
    })


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin_dashboard.html", {"request": request})


@router.get("/courses", response_class=HTMLResponse)
def courses_page(request: Request):
    return templates.TemplateResponse("courses.html", {"request": request})


@router.get("/course/{course_id}", response_class=HTMLResponse)
def course_detail_page(request: Request, course_id: int):
    return templates.TemplateResponse("course_detail.html", {"request": request, "course_id": course_id})


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    """Страница профиля пользователя (Мои данные)"""
    return templates.TemplateResponse("profile.html", {"request": request})