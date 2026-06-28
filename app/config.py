# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # === ОСНОВНЫЕ НАСТРОЙКИ ===
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/iro_courses")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-key-change-this-iro2024")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    ADMIN_SECRET_CODE: str = os.getenv("ADMIN_SECRET_CODE", "adminIRO3377")
    
    # === НАСТРОЙКИ MOODLE ===
    MOODLE_URL: str = os.getenv("MOODLE_URL", "http://localhost:8080")
    MOODLE_API_TOKEN: str = os.getenv("MOODLE_API_TOKEN", "704b71497c0923e6623d2f8b5daf725e")
    MOODLE_DEFAULT_COURSE_ID: int = int(os.getenv("MOODLE_DEFAULT_COURSE_ID", "2"))

settings = Settings()