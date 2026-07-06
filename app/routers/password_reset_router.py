# app/routers/password_reset_router.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime, timedelta
import secrets
import re

from app.database import get_db
from app import models, auth
from app.services.email_service import email_service
from app.config import settings

router = APIRouter(prefix="/api/password-reset", tags=["Password Reset"])
# ❌ Убираем templates - страницы теперь в public_router
# templates = Jinja2Templates(directory="app/templates")


# ============================================================
# СХЕМЫ (Pydantic)
# ============================================================

class PasswordResetRequest(BaseModel):
    """Схема для запроса сброса пароля (ввод email)"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Схема для подтверждения сброса пароля (новый пароль)"""
    token: str
    new_password: str
    confirm_password: str
    
    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Проверка силы пароля (те же требования, что при регистрации)"""
        if len(v) < 8:
            raise ValueError('Пароль должен содержать минимум 8 символов')
        
        if not re.search(r'\d', v):
            raise ValueError('Пароль должен содержать хотя бы одну цифру')
        
        if not re.search(r'[A-ZА-Я]', v):
            raise ValueError('Пароль должен содержать хотя бы одну заглавную букву')
        
        if not re.search(r'[a-zа-я]', v):
            raise ValueError('Пароль должен содержать хотя бы одну строчную букву')
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Пароль должен содержать хотя бы один специальный символ (!@#$%^&*() etc.)')
        
        return v
    
    @field_validator('confirm_password')
    @classmethod
    def validate_password_match(cls, v: str, info) -> str:
        """Проверка совпадения паролей"""
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('Пароли не совпадают')
        return v


# ============================================================
# ❌ УДАЛЯЕМ HTML СТРАНИЦЫ (они теперь в public_router)
# ============================================================
# @router.get("/forgot-password", response_class=HTMLResponse)  <- УДАЛЕНО
# async def forgot_password_page(request: Request): ...
# 
# @router.get("/reset-password", response_class=HTMLResponse)  <- УДАЛЕНО
# async def reset_password_page(request: Request, token: str = None): ...


# ============================================================
# API ЭНДПОИНТЫ
# ============================================================

@router.post("/request")
async def request_password_reset(
    request_data: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """
    Запрос на сброс пароля.
    1. Проверяет, существует ли пользователь с таким email
    2. Если существует - генерирует токен и отправляет письмо
    3. ВСЕГДА возвращает одинаковый ответ (безопасность - не раскрываем информацию о существовании email)
    """
    # Ищем пользователя по email
    user = db.query(models.User).filter(models.User.email == request_data.email).first()
    
    # ВСЕГДА возвращаем одинаковое сообщение (даже если пользователь не найден)
    # Это защита от перебора email'ов
    success_message = "Если email зарегистрирован, ссылка для сброса пароля отправлена на вашу почту."
    
    if not user:
        # Пользователь не найден - просто возвращаем успешный ответ
        return {"message": success_message}
    
    # Проверяем, не заблокирован ли пользователь
    if user.is_blocked:
        # Даже если заблокирован - возвращаем то же сообщение
        return {"message": success_message}
    
    try:
        # Генерируем безопасный токен
        token = secrets.token_urlsafe(32)
        
        # Время жизни токена (из настроек или 60 минут по умолчанию)
        expires_minutes = getattr(settings, 'RESET_TOKEN_EXPIRE_MINUTES', 60)
        expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)
        
        # Создаем запись в БД
        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=expires_at,
            used=False
        )
        db.add(reset_token)
        db.commit()
        
        # Формируем ссылку для сброса
        # Определяем базовый URL из настроек
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        reset_link = f"{base_url}/reset-password?token={token}"
        
        # Отправляем письмо
        email_sent = email_service.send_password_reset_email(
            to_email=user.email,
            full_name=user.full_name,
            reset_link=reset_link
        )
        
        if not email_sent:
            # Если письмо не отправлено - логируем, но пользователю все равно возвращаем успех
            # (чтобы не раскрывать информацию о состоянии)
            print(f"⚠️ Failed to send password reset email to {user.email}")
        
        return {"message": success_message}
        
    except Exception as e:
        # Логируем ошибку, но пользователю возвращаем успех
        print(f"❌ Password reset error: {str(e)}")
        db.rollback()
        return {"message": success_message}


@router.post("/reset")
async def reset_password(
    request_data: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    """
    Установка нового пароля.
    1. Проверяет токен (существует, не истек, не использован)
    2. Обновляет пароль пользователя
    3. Помечает токен как использованный
    """
    # Ищем токен в БД
    reset_token = db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.token == request_data.token,
        models.PasswordResetToken.used == False,
        models.PasswordResetToken.expires_at > datetime.utcnow()
    ).first()
    
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ссылка для сброса пароля недействительна или истекла. Пожалуйста, запросите сброс повторно."
        )
    
    # Получаем пользователя
    user = db.query(models.User).filter(models.User.id == reset_token.user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь не найден"
        )
    
    # Проверяем, не заблокирован ли пользователь
    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ваш аккаунт заблокирован. Обратитесь в поддержку."
        )
    
    try:
        # Хешируем новый пароль
        hashed_password = auth.get_password_hash(request_data.new_password)
        user.hashed_password = hashed_password
        
        # Помечаем токен как использованный
        reset_token.used = True
        
        db.commit()
        
        return {"message": "Пароль успешно изменен. Теперь вы можете войти в систему с новым паролем."}
        
    except Exception as e:
        db.rollback()
        print(f"❌ Password reset error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла ошибка при сбросе пароля. Пожалуйста, попробуйте позже."
        )


@router.get("/check-token/{token}")
async def check_reset_token(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Проверка валидности токена (используется на странице сброса для предварительной проверки).
    """
    reset_token = db.query(models.PasswordResetToken).filter(
        models.PasswordResetToken.token == token,
        models.PasswordResetToken.used == False,
        models.PasswordResetToken.expires_at > datetime.utcnow()
    ).first()
    
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ссылка для сброса пароля недействительна или истекла."
        )
    
    return {"valid": True, "user_id": reset_token.user_id}