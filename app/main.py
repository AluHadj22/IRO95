from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from app.database import engine, Base
from app.routers import auth_router, courses_router, admin_router, notifications_router, public_router, achievements_router
from app.routers import lms_router
from app.routers import profile_router  # ✅ ДОБАВЛЯЕМ ИМПОРТ
import os

# Создаём таблицы в базе данных
Base.metadata.create_all(bind=engine)

# Создаём папки для статических файлов, если их нет
os.makedirs("app/static/uploads/courses", exist_ok=True)
os.makedirs("app/static/uploads/speakers", exist_ok=True)
os.makedirs("app/static/uploads/profile/documents", exist_ok=True)  # ✅ ДОБАВЛЯЕМ

# Настройка шаблонов
templates = Jinja2Templates(directory="app/templates")

app = FastAPI(
    title="ИРО ЧР - Платформа повышения квалификации",
    description="Платформа для регистрации на курсы повышения квалификации",
    version="1.0.0"
)

# Настройка CORS для экспорта Excel и других запросов
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Подключаем статические файлы (CSS, JS, загруженные изображения)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Подключаем роутеры
app.include_router(auth_router.router)
app.include_router(courses_router.router)
app.include_router(admin_router.router)
app.include_router(notifications_router.router)
app.include_router(public_router.router)
app.include_router(achievements_router.router)
app.include_router(lms_router.router)
app.include_router(profile_router.router)  # ✅ ДОБАВЛЯЕМ ПОДКЛЮЧЕНИЕ


@app.get("/")
def root():
    return {"message": "API is running", "status": "healthy"}


@app.get("/map")
async def map_page(request: Request):
    """Страница с картой в полноэкранном режиме"""
    return templates.TemplateResponse("map.html", {"request": request})


@app.get("/health")
def health():
    return {"status": "ok"}