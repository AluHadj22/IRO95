from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app import models
from app.database import get_db
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


# === ХЕШИРОВАНИЕ ПАРОЛЯ (БЕЗ ОБРЕЗАНИЯ) ===
def get_password_hash(password: str) -> str:
    """Хеширует пароль с помощью bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет пароль."""
    return pwd_context.verify(plain_password, hashed_password)


# === СОЗДАНИЕ JWT ТОКЕНА ===
def create_access_token(data: dict) -> str:
    """Создаёт JWT токен с audience и iat."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "aud": "iro-platform"
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# === ПРОВЕРКА АДМИН-КОДА ===
def check_admin_code(code: str) -> bool:
    return code == settings.ADMIN_SECRET_CODE


# === ПОЛУЧЕНИЕ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ ===
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    Получает текущего пользователя по JWT токену.
    ✅ Проверяет audience (aud)
    ✅ Обрабатывает все ошибки JWT явно
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience="iro-platform"
        )
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTError as e:
        # В python-jose все ошибки JWT попадают сюда
        error_msg = str(e)
        if "audience" in error_msg.lower() or "aud" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {error_msg}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


# === ОПЦИОНАЛЬНАЯ АВТОРИЗАЦИЯ ===
def get_current_user_optional(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    Опциональная авторизация - не выдаёт ошибку если нет токена или он невалидный.
    """
    if not token:
        return None
    
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience="iro-platform"
        )
        email = payload.get("sub")
        if not email:
            return None
    except jwt.JWTError:
        return None
    except Exception:
        return None
    
    user = db.query(models.User).filter(models.User.email == email).first()
    return user


# === ТЕКУЩИЙ АКТИВНЫЙ ПОЛЬЗОВАТЕЛЬ ===
def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    """Проверяет, что пользователь не заблокирован."""
    if current_user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account blocked"
        )
    return current_user


# === ТЕКУЩИЙ АДМИНИСТРАТОР ===
def get_current_admin(current_user: models.User = Depends(get_current_active_user)):
    """Проверяет, что пользователь является администратором."""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user