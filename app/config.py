# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()


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
    
    def __init__(self):
        # Проверяем обязательные переменные
        required_vars = {
            "DATABASE_URL": self.DATABASE_URL,
            "SECRET_KEY": self.SECRET_KEY,
            "ADMIN_SECRET_CODE": self.ADMIN_SECRET_CODE,
            "MOODLE_URL": self.MOODLE_URL,
            "MOODLE_API_TOKEN": self.MOODLE_API_TOKEN,
            "ENCRYPTION_KEY": self.ENCRYPTION_KEY,
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