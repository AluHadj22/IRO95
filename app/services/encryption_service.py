# app/services/encryption_service.py
from cryptography.fernet import Fernet
from app.config import settings


class EncryptionService:
    def __init__(self):
        self.cipher = Fernet(settings.ENCRYPTION_KEY.encode())
    
    def encrypt(self, value: str) -> str:
        if not value:
            return None
        return self.cipher.encrypt(value.encode()).decode()
    
    def decrypt(self, value: str) -> str:
        if not value:
            return None
        return self.cipher.decrypt(value.encode()).decode()