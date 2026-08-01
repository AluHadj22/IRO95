# app/dependencies.py
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_async_db
from app import auth, models

# ============================================================
# ОБЩИЕ ЗАВИСИМОСТИ (АСИНХРОННЫЕ)
# ============================================================

# Асинхронная сессия БД
CommonDB = Depends(get_async_db)

# Текущий пользователь (асинхронный)
CurrentUser = Depends(auth.get_current_active_user)

# Текущий администратор (асинхронный)
CurrentAdmin = Depends(auth.get_current_admin)

# Опциональный пользователь (асинхронный)
OptionalUser = Depends(auth.get_current_user_optional)


# ============================================================
# ПРОВЕРКА ЗАПОЛНЕННОСТИ ПРОФИЛЯ (АСИНХРОННАЯ)
# ============================================================

async def require_complete_profile(  # ← async def
    current_user: models.User = Depends(auth.get_current_active_user),
    db: AsyncSession = Depends(get_async_db)  # ← асинхронная сессия
) -> models.User:
    """
    Проверяет, заполнен ли профиль пользователя полностью.
    Если нет - выбрасывает исключение с деталями о незаполненных разделах.
    
    Используется в эндпоинтах, где требуется полностью заполненный профиль
    (например, запись на курсы).
    
    Returns:
        models.User: Текущий пользователь, если профиль заполнен
    
    Raises:
        HTTPException 403: С деталями о незаполненных разделах
    """
    # Используем метод модели для получения детальной информации
    # (синхронный метод, не требует await)
    completion_details = current_user.get_profile_completion_details()
    
    if not completion_details["is_complete"]:
        # Получаем список незаполненных разделов
        missing_sections = []
        for section in completion_details["sections"]:
            if not section["is_complete"]:
                missing_sections.append({
                    "section": section["section"],
                    "label": section["label"],
                    "fields": section["fields"]
                })
        
        # Формируем понятное сообщение
        section_names = [s["label"] for s in missing_sections]
        message = f"Для записи на курс необходимо заполнить: {', '.join(section_names)}"
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "profile_incomplete",
                "message": message,
                "missing_sections": missing_sections,
                "redirect": "/profile"
            }
        )
    
    return current_user


# ============================================================
# ОПЦИОНАЛЬНАЯ ПРОВЕРКА ПРОФИЛЯ (АСИНХРОННАЯ)
# ============================================================

async def check_profile_complete_optional(  # ← async def
    current_user: models.User = Depends(auth.get_current_active_user),
    db: AsyncSession = Depends(get_async_db)  # ← асинхронная сессия
) -> dict:
    """
    Проверяет профиль и возвращает детальную информацию без выбрасывания исключения.
    Используется в эндпоинтах, где нужно только проверить статус.
    """
    # Синхронный метод модели, не требует await
    return current_user.get_profile_completion_details()