import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./iro_courses.db")

#  НАСТРОЙКА ПУЛА СОЕДИНЕНИЙ ДЛЯ POSTGRESQL
# Эти параметры находятся в переменных окружения, чтобы их можно было менять без изменения кода.
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "30"))              # Постоянные соединения в пуле
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))        # Дополнительные при пике
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))        # Таймаут ожидания соединения
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))      # Пересоздавать через час
POOL_PRE_PING = os.getenv("DB_POOL_PRE_PING", "True").lower() == "true"

#  ОПРЕДЕЛЯЕМ ТИП БД 
is_sqlite = "sqlite" in DATABASE_URL
is_postgres = "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL

if is_sqlite:
    # SQLite — пул не нужен, используем стандартные настройки
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
        pool_size=1,           # SQLite не поддерживает многопоточные соединения
        max_overflow=0,
        pool_timeout=30,
    )
else:
    # PostgreSQL с полноценным пулом
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        # === НАСТРОЙКИ ПУЛА ===
        pool_size=POOL_SIZE,                    # Базовое количество соединений
        max_overflow=MAX_OVERFLOW,              # Дополнительные при нагрузке
        pool_timeout=POOL_TIMEOUT,              # Таймаут ожидания свободного соединения
        pool_recycle=POOL_RECYCLE,              # Пересоздавать старые соединения
        pool_pre_ping=POOL_PRE_PING,            # Проверять соединение перед использованием
        # ДОП НАСТРОЙКИ
        pool_use_lifo=True,                     # LIFO — свежие соединения используются первыми
        echo_pool=False,                        # Не логируем работу пула (для продакшена)
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Генератор для получения сессии БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()