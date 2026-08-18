# app/routers/auth_router.py
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address
from app import models, schemas, auth
from app.database import get_async_db

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# === RATE LIMITER (ЗАЩИТА ОТ БРУТФОРСА) ===
limiter = Limiter(key_func=get_remote_address)


@router.post("/register")
@limiter.limit("5/minute")  #  Не более 5 регистраций с одного IP в минуту
async def register(  # ← async def
    request: Request,
    user: schemas.UserCreate,
    db: AsyncSession = Depends(get_async_db)  # ← асинхронная сессия
):
    """
    Регистрация нового пользователя.
         Rate limiting: 5 запросов в минуту с одного IP
         Проверка на существующий email
         Поддержка админ-кода
         Выбор должности при регистрации
    """
    # Проверка на существующего пользователя (асинхронно)
    stmt = select(models.User).where(models.User.email == user.email)
    result = await db.execute(stmt)  # ← await
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # ============================================================
    # ОПРЕДЕЛЯЕМ ТЕХНИЧЕСКУЮ РОЛЬ (права доступа)
    # ============================================================
    role = models.UserRole.ADMIN if user.admin_code and auth.check_admin_code(user.admin_code) else models.UserRole.TEACHER
    
    # ============================================================
    # ОПРЕДЕЛЯЕМ ДОЛЖНОСТЬ (информационная)
    # ============================================================
    position_value = None
    
    # Если выбран тип должности
    if user.position_type:
        if user.position_type == 'Иное':
            # Если выбрано "Иное" - используем кастомное значение
            position_value = user.position_custom
        else:
            # Иначе используем выбранный тип
            position_value = user.position_type
    elif user.position:
        # Если передан position напрямую (обратная совместимость)
        position_value = user.position
    
    # Хешируем пароль
    hashed_password = auth.get_password_hash(user.password)
    
    # Создаём пользователя
    db_user = models.User(
        email=user.email,
        full_name=user.full_name,
        position=position_value,
        phone=user.phone,
        organization=user.organization,
        hashed_password=hashed_password,
        role=role
    )
    
    db.add(db_user)
    await db.commit()  # ← await
    await db.refresh(db_user)  # ← await
    
    # Получаем понятное отображение роли
    role_display = db_user.get_role_display()
    
    return {
        "message": f"User registered successfully as {role_display}",
        "role": role.value,
        "role_display": role_display,
        "position": position_value,
        "user_id": db_user.id
    }


@router.post("/login")
@limiter.limit("5/minute")  #  Не более 5 попыток входа с одного IP в минуту
async def login(  # ← async def
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_async_db)  # ← асинхронная сессия
):
    """
    Вход в систему.
         Rate limiting: 5 попыток в минуту с одного IP
         Проверка пароля
         Проверка блокировки
         Возвращает JWT токен
    """
    # Ищем пользователя по email (асинхронно)
    stmt = select(models.User).where(models.User.email == form_data.username)
    result = await db.execute(stmt)  # ← await
    user = result.scalar_one_or_none()
    
    # Проверяем пароль
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        #  Не уточняем, что именно неверно (email или пароль) - безопасность
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Проверяем блокировку
    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account blocked. Please contact support."
        )
    
    # Создаём JWT токен (с aud и iat)
    access_token = auth.create_access_token(data={"sub": user.email})
    
    # Получаем понятное отображение роли
    role_display = user.get_role_display()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role.value,
        "role_display": role_display,
        "position": user.position,
        "user_id": user.id
    }


@router.get("/me")
async def get_current_user(  # ← async def
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Получение данных текущего пользователя.
      Требует валидный JWT токен
      Возвращает только необходимые данные
    """
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
        "role_display": current_user.get_role_display(),
        "position": current_user.position,
        "position_display": current_user.get_position_display(),
        "is_blocked": current_user.is_blocked,
        "is_admin": current_user.is_admin,
        "phone": current_user.phone,
        "organization": current_user.organization,
        "created_at": current_user.created_at
    }