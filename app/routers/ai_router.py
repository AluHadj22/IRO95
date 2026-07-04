# app/routers/ai_router.py
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel
import logging

from app.database import get_db
from app.auth import get_current_user
from app.models import User
from app.services.ai_service import get_ai_response

logger = logging.getLogger(__name__)

# ✅ ВАЖНО: префикс должен быть /api/ai, чтобы соответствовать frontend
router = APIRouter(prefix="/api/ai", tags=["AI"])

# Подключаем шаблоны
templates = Jinja2Templates(directory="app/templates")


class AIRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = None


class AIResponse(BaseModel):
    success: bool
    response: str
    model: Optional[str] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None


# ============================================================
# СТРАНИЦА ЧАТА (GET)
# ============================================================

@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """
    Страница чата с ИИ-ассистентом.
    Доступна только для авторизованных пользователей.
    """
    return templates.TemplateResponse("ai_chat.html", {"request": request})


# ============================================================
# API ЭНДПОИНТЫ
# ============================================================

@router.post("/chat")
async def chat(
    request: AIRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Чат с ИИ-ассистентом (API эндпоинт).
    """
    try:
        # Логируем запрос
        logger.info(f"AI chat request from user {current_user.id}: {request.message[:100]}...")
        
        # Проверяем, что сообщение не пустое
        if not request.message or not request.message.strip():
            return {
                "success": False,
                "response": "Пожалуйста, введите ваш вопрос.",
                "error": "Empty message"
            }
        
        # Проверяем длину сообщения
        if len(request.message) > 2000:
            return {
                "success": False,
                "response": "Сообщение слишком длинное (макс. 2000 символов).",
                "error": "Message too long"
            }
        
        # Получаем ответ от ИИ
        result = get_ai_response(
            message=request.message,
            history=request.history,
            db=db
        )
        
        # Проверяем, что result не None
        if result is None:
            logger.error(f"AI service returned None for user {current_user.id}")
            return {
                "success": False,
                "response": "⚠️ Сервис ИИ временно недоступен. Пожалуйста, попробуйте позже.",
                "error": "AI service returned None"
            }
        
        # Безопасно получаем response
        response_text = result.get('response')
        if response_text is None:
            logger.error(f"AI service returned response=None for user {current_user.id}")
            response_text = "⚠️ Извините, произошла ошибка при генерации ответа. Попробуйте еще раз."
        
        # Безопасно получаем model
        model_name = result.get('model')
        if model_name is None:
            model_name = "unknown"
        
        # Безопасно получаем timestamp
        timestamp = result.get('timestamp')
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        # Логируем успешный ответ
        logger.info(f"AI chat response for user {current_user.id}: model={model_name}, response_len={len(response_text)}")
        
        # Возвращаем ответ
        return {
            "success": True,
            "response": response_text,
            "model": model_name,
            "timestamp": timestamp
        }
        
    except Exception as e:
        logger.error(f"Error in AI chat: {str(e)}", exc_info=True)
        return {
            "success": False,
            "response": "❌ Произошла ошибка при обработке запроса. Пожалуйста, обратитесь в службу поддержки: ipkro-chr@mail.ru",
            "error": str(e)
        }


@router.get("/health")
async def health_check():
    """
    Проверка статуса ИИ-сервиса.
    """
    try:
        # Проверяем, что сервис доступен
        result = get_ai_response(
            message="Привет",
            db=None
        )
        
        if result and result.get('response'):
            return {
                "status": "ok",
                "message": "AI service is available",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "status": "degraded",
                "message": "AI service is available but returned unexpected response",
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        logger.error(f"AI health check failed: {str(e)}")
        return {
            "status": "error",
            "message": f"AI service is unavailable: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }