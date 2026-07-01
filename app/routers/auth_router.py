from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app import models, schemas, auth
from app.database import get_db

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# === RATE LIMITER (ЗАЩИТА ОТ БРУТФОРСА) ===
# Используем глобальный limiter из main.py или создаём локальный
# Если в main.py уже есть limiter, используем его через Depends
limiter = Limiter(key_func=get_remote_address)


@router.post("/register")
@limiter.limit("5/minute")  # ✅ Не более 5 регистраций с одного IP в минуту
def register(
    request: Request,  # ✅ Добавляем Request для rate limiting
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    """
    Регистрация нового пользователя.
    ✅ Rate limiting: 5 запросов в минуту с одного IP
    ✅ Проверка на существующий email
    ✅ Поддержка админ-кода
    """
    # Проверка на существующего пользователя
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Определяем роль (админ или преподаватель)
    role = models.UserRole.ADMIN if user.admin_code and auth.check_admin_code(user.admin_code) else models.UserRole.TEACHER
    
    # Хешируем пароль (уже без обрезания)
    hashed_password = auth.get_password_hash(user.password)
    
    # Создаём пользователя
    db_user = models.User(
        email=user.email,
        full_name=user.full_name,
        position=user.position,
        phone=user.phone,
        organization=user.organization,
        hashed_password=hashed_password,
        role=role
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # ✅ Логируем успешную регистрацию (без чувствительных данных)
    # В будущем добавить логирование
    
    return {
        "message": "User registered successfully",
        "role": role.value,
        "user_id": db_user.id
    }


@router.post("/login")
@limiter.limit("5/minute")  # ✅ Не более 5 попыток входа с одного IP в минуту
def login(
    request: Request,  # ✅ Добавляем Request для rate limiting
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Вход в систему.
    ✅ Rate limiting: 5 попыток в минуту с одного IP
    ✅ Проверка пароля
    ✅ Проверка блокировки
    ✅ Возвращает JWT токен
    """
    # Ищем пользователя по email
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    
    # Проверяем пароль
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        # ✅ Не уточняем, что именно неверно (email или пароль) - безопасность
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
    
    # ✅ Логируем успешный вход (без чувствительных данных)
    # В будущем добавить логирование
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role.value,
        "user_id": user.id
    }


@router.get("/me")
def get_current_user(
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Получение данных текущего пользователя.
    ✅ Требует валидный JWT токен
    ✅ Возвращает только необходимые данные
    """
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
        "is_blocked": current_user.is_blocked,
        "position": current_user.position,
        "phone": current_user.phone,
        "organization": current_user.organization,
        "created_at": current_user.created_at
    }