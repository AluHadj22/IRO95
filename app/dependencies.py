from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app import auth

# Общие зависимости
CommonDB = Depends(get_db)
CurrentUser = Depends(auth.get_current_active_user)
CurrentAdmin = Depends(auth.get_current_admin)
OptionalUser = Depends(auth.get_current_user_optional)