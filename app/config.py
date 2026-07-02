# app/config.py
import os
from dotenv import load_dotenv
from pathlib import Path

# Явно указываем путь к .env для надежности
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class Settings:
    # === ОСНОВНЫЕ НАСТРОЙКИ ===
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    ADMIN_SECRET_CODE: str = os.getenv("ADMIN_SECRET_CODE")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # === ШИФРОВАНИЕ ДАННЫХ ===
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY")
    
    # === НАСТРОЙКИ MOODLE ===
    MOODLE_URL: str = os.getenv("MOODLE_URL")
    MOODLE_API_TOKEN: str = os.getenv("MOODLE_API_TOKEN")
    MOODLE_DEFAULT_COURSE_ID: int = int(os.getenv("MOODLE_DEFAULT_COURSE_ID", "2"))
    
    # === НАСТРОЙКИ SMTP ===
    SMTP_HOST: str = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "ИРО ЧР - Платформа повышения квалификации")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    
    def __init__(self):
        # Проверяем обязательные переменные
        required_vars = {
            "DATABASE_URL": self.DATABASE_URL,
            "SECRET_KEY": self.SECRET_KEY,
            "ADMIN_SECRET_CODE": self.ADMIN_SECRET_CODE,
            "MOODLE_URL": self.MOODLE_URL,
            "MOODLE_API_TOKEN": self.MOODLE_API_TOKEN,
            "ENCRYPTION_KEY": self.ENCRYPTION_KEY,
            "SMTP_HOST": self.SMTP_HOST,
            "SMTP_USER": self.SMTP_USER,
            "SMTP_PASSWORD": self.SMTP_PASSWORD,
            "SMTP_FROM_EMAIL": self.SMTP_FROM_EMAIL,
        }
        
        missing = [key for key, value in required_vars.items() if not value]
        if missing:
            raise ValueError(
                f"❌ Обязательные переменные окружения не заданы:\n"
                f"   {', '.join(missing)}\n\n"
                f"Добавьте их в файл .env или установите как переменные окружения."
            )
        
        # Проверяем длину SECRET_KEY
        if len(self.SECRET_KEY) < 32:
            raise ValueError(
                f"❌ SECRET_KEY слишком короткий (минимум 32 символа).\n"
                f"Сгенерируйте новый: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        
        # Проверяем ENCRYPTION_KEY
        try:
            from cryptography.fernet import Fernet
            Fernet(self.ENCRYPTION_KEY.encode())
        except ImportError:
            raise ImportError(
                "❌ Установите cryptography: pip install cryptography"
            )
        except Exception:
            raise ValueError(
                f"❌ ENCRYPTION_KEY невалидный.\n"
                f"Сгенерируйте новый: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )


settings = Settings()

# Выводим настройки для проверки (без паролей)
print(f"🔍 MOODLE_URL: {settings.MOODLE_URL}")
print(f"🔍 MOODLE_API_TOKEN: {settings.MOODLE_API_TOKEN[:10]}...")
print(f"🔍 SMTP_HOST: {settings.SMTP_HOST}")
print(f"🔍 SMTP_USER: {settings.SMTP_USER}")
print(f"🔍 SMTP_FROM_EMAIL: {settings.SMTP_FROM_EMAIL}")