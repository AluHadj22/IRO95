# app/schemas.py
from pydantic import BaseModel, EmailStr, Field, validator
from datetime import datetime, date
from typing import Optional, List, Any, Union
from enum import Enum


class UserRole(str, Enum):
    TEACHER = "teacher"
    ADMIN = "admin"


# ========== АУТЕНТИФИКАЦИЯ ==========

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    position: Optional[str] = None
    phone: Optional[str] = None
    organization: Optional[str] = None
    password: str = Field(..., min_length=6)
    admin_code: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    position: Optional[str]
    phone: Optional[str]
    organization: Optional[str]
    role: str
    is_blocked: bool
    created_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


# ========== КАТЕГОРИИ ==========

class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    courses_count: int = 0
    
    class Config:
        from_attributes = True


# ========== СПИКЕРЫ ==========

class SpeakerCreate(BaseModel):
    full_name: str
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    position: Optional[str] = None


class SpeakerResponse(BaseModel):
    id: int
    full_name: str
    bio: Optional[str]
    photo_url: Optional[str]
    position: Optional[str]
    
    class Config:
        from_attributes = True


# ========== КУРСЫ ==========

class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    category_id: Optional[int] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    video_platform: str = "youtube"
    hashtags: Optional[str] = None
    keywords: Optional[str] = None
    max_participants: int = 100
    format_type: str = "online"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_open_ended: bool = False
    moodle_course_id: Optional[int] = None
    speakers: List[SpeakerCreate] = []


class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    category_id: Optional[int] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    video_platform: Optional[str] = None
    hashtags: Optional[str] = None
    keywords: Optional[str] = None
    max_participants: Optional[int] = None
    format_type: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_open_ended: Optional[bool] = None
    is_active: Optional[bool] = None
    moodle_course_id: Optional[int] = None


class CourseResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    short_description: Optional[str]
    category_id: Optional[int]
    category_name: Optional[str]
    image_url: Optional[str]
    video_url: Optional[str]
    video_platform: Optional[str] = "youtube"
    hashtags: Optional[str]
    keywords: Optional[str]
    max_participants: int
    current_participants: int
    format_type: str = "online"
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    is_open_ended: bool = False
    is_active: bool
    moodle_course_id: Optional[int] = None
    speakers: List[SpeakerResponse] = []
    is_favorite: bool = False
    is_watch_later: bool = False
    
    class Config:
        from_attributes = True


# ========== УВЕДОМЛЕНИЯ ==========

class NotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# ========== ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ==========

# --- Личные данные ---

class PersonalDataUpdate(BaseModel):
    """Обновление личных данных"""
    last_name: Optional[str] = Field(None, max_length=100)
    first_name: Optional[str] = Field(None, max_length=100)
    middle_name: Optional[str] = Field(None, max_length=100)
    gender: Optional[str] = Field(None, pattern="^(male|female)$")
    birth_date: Optional[date] = None
    citizenship: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=200)
    municipality: Optional[str] = Field(None, max_length=200)
    phone_raw: Optional[str] = Field(None, max_length=20)
    consent_to_personal_data: Optional[bool] = None


class PersonalDataResponse(BaseModel):
    """Ответ с личными данными"""
    last_name: Optional[str]
    first_name: Optional[str]
    middle_name: Optional[str]
    gender: Optional[str]
    birth_date: Optional[date]
    citizenship: Optional[str]
    region: Optional[str]
    municipality: Optional[str]
    phone_raw: Optional[str]
    consent_to_personal_data: bool
    
    class Config:
        from_attributes = True


# --- Образование ---

# Список допустимых уровней образования
EDUCATION_LEVELS = [
    "Высшее",
    "Среднее профессиональное",
    "Среднее общее (студент)"
]


class EducationCreate(BaseModel):
    """Создание образования"""
    education_level: Optional[str] = Field(None, max_length=100)
    document_series: Optional[str] = Field(None, max_length=50)
    registration_number: Optional[str] = Field(None, max_length=50)
    qualification: Optional[str] = Field(None, max_length=500)
    document_number: Optional[str] = Field(None, max_length=50)
    issue_date: Optional[date] = None
    academic_degree: Optional[str] = Field(None, max_length=50)
    academic_title: Optional[str] = Field(None, max_length=50)
    diploma_last_name: Optional[str] = Field(None, max_length=100)
    diploma_first_name: Optional[str] = Field(None, max_length=100)
    diploma_middle_name: Optional[str] = Field(None, max_length=100)
    is_main: bool = False
    
    @validator('education_level')
    def validate_education_level(cls, v):
        if v and v not in EDUCATION_LEVELS:
            raise ValueError(f"Недопустимый уровень образования. Допустимые значения: {', '.join(EDUCATION_LEVELS)}")
        return v


class EducationUpdate(BaseModel):
    """Обновление образования"""
    education_level: Optional[str] = Field(None, max_length=100)
    document_series: Optional[str] = Field(None, max_length=50)
    registration_number: Optional[str] = Field(None, max_length=50)
    qualification: Optional[str] = Field(None, max_length=500)
    document_number: Optional[str] = Field(None, max_length=50)
    issue_date: Optional[date] = None
    academic_degree: Optional[str] = Field(None, max_length=50)
    academic_title: Optional[str] = Field(None, max_length=50)
    diploma_last_name: Optional[str] = Field(None, max_length=100)
    diploma_first_name: Optional[str] = Field(None, max_length=100)
    diploma_middle_name: Optional[str] = Field(None, max_length=100)
    is_main: Optional[bool] = None
    
    @validator('education_level')
    def validate_education_level(cls, v):
        if v and v not in EDUCATION_LEVELS:
            raise ValueError(f"Недопустимый уровень образования. Допустимые значения: {', '.join(EDUCATION_LEVELS)}")
        return v


class EducationResponse(BaseModel):
    """Ответ с данными об образовании"""
    id: int
    user_id: int
    education_level: Optional[str]
    document_series: Optional[str]
    registration_number: Optional[str]
    qualification: Optional[str]
    document_number: Optional[str]
    issue_date: Optional[date]
    academic_degree: Optional[str]
    academic_title: Optional[str]
    diploma_last_name: Optional[str]
    diploma_first_name: Optional[str]
    diploma_middle_name: Optional[str]
    is_main: bool
    diploma_file_url: Optional[str]
    diploma_file_name: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# --- Работа ---

# Список допустимых видов деятельности
ACTIVITY_TYPES = [
    "Управленческие кадры",
    "Педагогические работники",
    "Специалисты системы ДПО",
    "Органы управления образованием"
]


class WorkCreate(BaseModel):
    """Создание места работы"""
    organization: Optional[str] = Field(None, max_length=500)
    organization_inn: Optional[str] = Field(None, max_length=50)
    work_experience_years: Optional[int] = Field(None, ge=0)
    teaching_experience_years: Optional[int] = Field(None, ge=0)
    organization_type: Optional[str] = Field(None, max_length=200)
    position: Optional[str] = Field(None, max_length=200)
    activity_type: str = Field(..., max_length=200, min_length=1, description="Вид деятельности (обязательно)")
    civil_service_status: Optional[str] = Field(None, max_length=100)
    subjects: List[str] = Field(..., min_length=1, description="Предметы (обязательно, минимум 1)")
    is_urban: bool = False
    is_rural: bool = False
    is_shnor: bool = False
    is_current: bool = True
    work_start_date: Optional[date] = None
    work_end_date: Optional[date] = None
    
    @validator('activity_type')
    def validate_activity_type(cls, v):
        if v not in ACTIVITY_TYPES:
            raise ValueError(f"Недопустимый вид деятельности. Допустимые значения: {', '.join(ACTIVITY_TYPES)}")
        return v


class WorkUpdate(BaseModel):
    """Обновление места работы"""
    organization: Optional[str] = Field(None, max_length=500)
    organization_inn: Optional[str] = Field(None, max_length=50)
    work_experience_years: Optional[int] = Field(None, ge=0)
    teaching_experience_years: Optional[int] = Field(None, ge=0)
    organization_type: Optional[str] = Field(None, max_length=200)
    position: Optional[str] = Field(None, max_length=200)
    activity_type: Optional[str] = Field(None, max_length=200)
    civil_service_status: Optional[str] = Field(None, max_length=100)
    subjects: Optional[List[str]] = None
    is_urban: Optional[bool] = None
    is_rural: Optional[bool] = None
    is_shnor: Optional[bool] = None
    is_current: Optional[bool] = None
    work_start_date: Optional[date] = None
    work_end_date: Optional[date] = None
    
    @validator('activity_type')
    def validate_activity_type(cls, v):
        if v and v not in ACTIVITY_TYPES:
            raise ValueError(f"Недопустимый вид деятельности. Допустимые значения: {', '.join(ACTIVITY_TYPES)}")
        return v


class WorkResponse(BaseModel):
    """Ответ с данными о работе"""
    id: int
    user_id: int
    organization: Optional[str]
    organization_inn: Optional[str]
    work_experience_years: Optional[int]
    teaching_experience_years: Optional[int]
    organization_type: Optional[str]
    position: Optional[str]
    activity_type: Optional[str]
    civil_service_status: Optional[str]
    subjects: Optional[List[str]]
    is_urban: bool
    is_rural: bool
    is_shnor: bool
    is_current: bool
    work_start_date: Optional[date]
    work_end_date: Optional[date]
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# --- Почтовый адрес ---

class AddressCreate(BaseModel):
    """Создание почтового адреса"""
    postal_index: Optional[str] = Field(None, max_length=10)
    region: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=200)
    street: Optional[str] = Field(None, max_length=300)
    house: Optional[str] = Field(None, max_length=50)
    building: Optional[str] = Field(None, max_length=50)
    structure: Optional[str] = Field(None, max_length=50)
    apartment: Optional[str] = Field(None, max_length=50)
    is_main: bool = True


class AddressUpdate(BaseModel):
    """Обновление почтового адреса"""
    postal_index: Optional[str] = Field(None, max_length=10)
    region: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=200)
    street: Optional[str] = Field(None, max_length=300)
    house: Optional[str] = Field(None, max_length=50)
    building: Optional[str] = Field(None, max_length=50)
    structure: Optional[str] = Field(None, max_length=50)
    apartment: Optional[str] = Field(None, max_length=50)
    is_main: Optional[bool] = None


class AddressResponse(BaseModel):
    """Ответ с почтовым адресом"""
    id: int
    user_id: int
    postal_index: Optional[str]
    region: Optional[str]
    city: Optional[str]
    street: Optional[str]
    house: Optional[str]
    building: Optional[str]
    structure: Optional[str]
    apartment: Optional[str]
    is_main: bool
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# --- Дополнительная информация ---

class AdditionalInfoUpdate(BaseModel):
    """Обновление дополнительной информации"""
    snils: Optional[str] = Field(None, max_length=20)
    passport_series: Optional[str] = Field(None, max_length=10)
    passport_number: Optional[str] = Field(None, max_length=20)
    passport_issued_by: Optional[str] = Field(None, max_length=500)
    passport_issued_date: Optional[date] = None
    passport_department_code: Optional[str] = Field(None, max_length=20)
    inn: Optional[str] = Field(None, max_length=20)
    data_confirmed: Optional[bool] = None


class AdditionalInfoResponse(BaseModel):
    """Ответ с дополнительной информацией"""
    id: int
    user_id: int
    snils: Optional[str]
    snils_file_url: Optional[str]
    snils_file_name: Optional[str]
    passport_series: Optional[str]
    passport_number: Optional[str]
    passport_issued_by: Optional[str]
    passport_issued_date: Optional[date]
    passport_department_code: Optional[str]
    passport_file_url: Optional[str]
    passport_file_name: Optional[str]
    inn: Optional[str]
    inn_file_url: Optional[str]
    inn_file_name: Optional[str]
    marriage_certificate_file_url: Optional[str]
    marriage_certificate_file_name: Optional[str]
    data_confirmed: bool
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


# --- Полный профиль ---

class FullProfileResponse(BaseModel):
    """Полный ответ с профилем пользователя"""
    user: UserResponse
    personal_data: PersonalDataResponse
    education: List[EducationResponse] = []
    work: List[WorkResponse] = []
    address: Optional[AddressResponse] = None
    additional_info: Optional[AdditionalInfoResponse] = None
    is_profile_complete: bool
    
    class Config:
        from_attributes = True


# --- Загрузка файлов ---

class FileUploadResponse(BaseModel):
    """Ответ при загрузке файла"""
    url: str
    filename: str
    file_size: int
    file_type: str
    message: str


# ========== ПРОВЕРКА ПРОФИЛЯ ==========

class ProfileCompleteCheck(BaseModel):
    """Проверка заполненности профиля"""
    is_complete: bool
    missing_fields: List[str] = []
    message: str