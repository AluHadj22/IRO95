from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import auth_router, courses_router, admin_router, notifications_router, public_router, achievements_router
import os

# Создаём таблицы в базе данных
Base.metadata.create_all(bind=engine)

# Создаём папки для статических файлов, если их нет
os.makedirs("app/static/uploads/courses", exist_ok=True)
os.makedirs("app/static/uploads/speakers", exist_ok=True)

app = FastAPI(
    title="ИРО ЧР - Платформа повышения квалификации",
    description="Платформа для регистрации на курсы повышения квалификации",
    version="1.0.0"
)

# Настройка CORS для экспорта Excel и других запросов
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Для production замените на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # Важно для скачивания файлов
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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "API is running", "status": "healthy"}