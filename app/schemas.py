from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

class UserRole(str, Enum):
    TEACHER = "teacher"
    ADMIN = "admin"


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
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


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


class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    category_id: Optional[int] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    video_platform: str = "youtube"  # youtube, vk, rutube
    hashtags: Optional[str] = None
    keywords: Optional[str] = None
    price: float = 0.0
    max_participants: int = 100
    format_type: str = "online"  # full_time, part_time, full_part_time, online
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_open_ended: bool = False
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
    price: Optional[float] = None
    max_participants: Optional[int] = None
    format_type: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_open_ended: Optional[bool] = None
    is_active: Optional[bool] = None


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
    price: float
    max_participants: int
    current_participants: int
    format_type: str = "online"
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    is_open_ended: bool = False
    is_active: bool
    speakers: List[SpeakerResponse] = []
    is_favorite: bool = False
    is_watch_later: bool = False
    
    class Config:
        from_attributes = True


class PaymentRequest(BaseModel):
    course_id: int


class PaymentResponse(BaseModel):
    success: bool
    message: str
    payment_id: Optional[str] = None


class NotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True