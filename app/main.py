from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.database import engine, Base
from app.routers import auth_router, courses_router, admin_router, notifications_router, public_router, achievements_router, ai_router
from app.routers import profile_router
from app.routers import password_reset_router
from app.config import settings
from app.scheduler import start_scheduler, stop_scheduler
import os
import re
import logging

class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = re.sub(r'"password":"[^"]*"', '"password":"***"', record.msg)
            record.msg = re.sub(r'"password":\s*"[^"]*"', '"password": "***"', record.msg)
            record.msg = re.sub(r'"snils":"[^"]*"', '"snils":"***"', record.msg)
            record.msg = re.sub(r'"snils":\s*"[^"]*"', '"snils": "***"', record.msg)
            record.msg = re.sub(r'"passport_series":"[^"]*"', '"passport_series":"***"', record.msg)
            record.msg = re.sub(r'"passport_number":"[^"]*"', '"passport_number":"***"', record.msg)
            record.msg = re.sub(r'"inn":"[^"]*"', '"inn":"***"', record.msg)
            record.msg = re.sub(r'"inn":\s*"[^"]*"', '"inn": "***"', record.msg)
            record.msg = re.sub(r'"access_token":"[^"]*"', '"access_token":"***"', record.msg)
            record.msg = re.sub(r'"token":"[^"]*"', '"token":"***"', record.msg)
        return True

logging.getLogger('uvicorn.access').addFilter(SensitiveDataFilter())
logging.getLogger('uvicorn.error').addFilter(SensitiveDataFilter())

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app = FastAPI(
    title="ИРО ЧР - Платформа повышения квалификации",
    description="Платформа для регистрации на курсы повышения квалификации",
    version="1.0.0",
    debug=settings.DEBUG
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    if settings.DEBUG:
        response.headers["Content-Security-Policy"] = (
            "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
            "script-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
            "style-src * 'unsafe-inline' data: blob:; "
            "img-src * data: blob:; "
            "font-src * data:; "
            "connect-src * data: blob:; "
            "frame-src *; "
            "worker-src * blob:; "
            "media-src *; "
            "object-src *; "
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' data: blob:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "https://cdn.jsdelivr.net "
            "https://unpkg.com "
            "https://api-maps.yandex.ru "
            "https://yastatic.net "
            "https://govzalla.ru "
            "https://core-renderer-tiles.maps.yandex.net; "
            "style-src 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net "
            "https://fonts.googleapis.com "
            "https://unpkg.com; "
            "img-src 'self' data: blob: https: http:; "
            "font-src 'self' "
            "https://cdn.jsdelivr.net "
            "https://fonts.gstatic.com "
            "data:; "
            "connect-src 'self' "
            "http://alu95.ru "
            "http://127.0.0.1:8000 "
            "https://api-maps.yandex.ru "
            "https://yastatic.net "
            "https://cdn.jsdelivr.net "
            "https://core-renderer-tiles.maps.yandex.net "
            "https://log.api-maps.yandex.ru; "
            "frame-src 'self' "
            "https://www.youtube.com "
            "https://youtu.be "
            "https://rutube.ru "
            "https://vk.com "
            "https://vkvideo.ru "
            "https://player.vk.com "
            "https://www.vk.com "
            "https://video.vk.com "
            "https://login.vk.com "
            "https://api.vk.com; "
            "worker-src 'self' blob:; "
            "media-src 'self' data: blob: https: http:; "
            "object-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
        )
    
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://alu95.ru",
        "https://www.alu95.ru",
        "https://irosdo.ru",
        "https://www.irosdo.ru",
        "https://iro-lms.ru",
        "https://www.iro-lms.ru",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

if not settings.DEBUG:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[
            "localhost",
            "127.0.0.1",
            "alu95.ru",
            "www.alu95.ru",
            "irosdo.ru",
            "www.irosdo.ru",
            "iro-lms.ru",
            "www.iro-lms.ru",
        ]
    )

Base.metadata.create_all(bind=engine)

os.makedirs("app/static/uploads/courses", exist_ok=True)
os.makedirs("app/static/uploads/speakers", exist_ok=True)
os.makedirs("app/static/uploads/profile/documents", exist_ok=True)

templates = Jinja2Templates(directory="app/templates")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router.router)
app.include_router(courses_router.router)
app.include_router(admin_router.router)
app.include_router(notifications_router.router)
app.include_router(public_router.router)
app.include_router(achievements_router.router)
app.include_router(profile_router.router)
app.include_router(ai_router.router)
app.include_router(password_reset_router.router)

@app.on_event("startup")
async def startup_event():
    logging.info("Запуск приложения...")
    try:
        start_scheduler()
        logging.info("Планировщик успешно запущен")
    except Exception as e:
        logging.error(f"Ошибка запуска планировщика: {str(e)}")

@app.on_event("shutdown")
async def shutdown_event():
    logging.info("Остановка приложения...")
    try:
        stop_scheduler()
        logging.info("Планировщик успешно остановлен")
    except Exception as e:
        logging.error(f"Ошибка остановки планировщика: {str(e)}")

@app.get("/map")
async def map_page(request: Request):
    return templates.TemplateResponse("map.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/test")
async def test():
    return {"status": "ok", "message": "Сервер работает!"}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc), "type": exc.__class__.__name__}
        )
    else:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )