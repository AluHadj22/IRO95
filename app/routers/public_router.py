from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, auth

router = APIRouter(tags=["Public"])
templates = Jinja2Templates(directory="app/templates")

# Добавляем функцию форматирования цены в шаблоны
def format_price(price):
    if price == 0:
        return "Бесплатно"
    return f"{int(price)} ₽"

templates.env.globals['formatPrice'] = format_price

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

@router.get("/course-modules/{course_id}", response_class=HTMLResponse)
async def course_modules_page(request: Request, course_id: int):
    return templates.TemplateResponse("course_modules.html", {"request": request, "course_id": course_id})


@router.get("/lesson/{lesson_id}", response_class=HTMLResponse)
async def lesson_page(request: Request, lesson_id: int):
    return templates.TemplateResponse("lesson_detail.html", {"request": request, "lesson_id": lesson_id})

@router.get("/lms-admin", response_class=HTMLResponse)
async def lms_admin_page(request: Request):
    return templates.TemplateResponse("lms_admin.html", {"request": request})