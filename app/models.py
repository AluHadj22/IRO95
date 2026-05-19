from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text, Enum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class UserRole(str, enum.Enum):
    TEACHER = "teacher"
    ADMIN = "admin"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    position = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    organization = Column(String(500), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.TEACHER)
    is_active = Column(Boolean, default=True)
    is_blocked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    favorite_courses = relationship("UserFavorite", back_populates="user", cascade="all, delete-orphan")
    watch_later = relationship("UserWatchLater", back_populates="user", cascade="all, delete-orphan")
    registrations = relationship("CourseRegistration", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), default="📁")
    color = Column(String(20), default="#667eea")
    order_index = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    courses = relationship("Course", back_populates="category", cascade="all, delete-orphan")

class Course(Base):
    __tablename__ = "courses"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    short_description = Column(String(200), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    image_url = Column(String(500), nullable=True)
    video_url = Column(String(500), nullable=True)
    hashtags = Column(String(500), nullable=True)
    keywords = Column(String(500), nullable=True)
    price = Column(Float, default=0.0)
    max_participants = Column(Integer, default=100)
    current_participants = Column(Integer, default=0)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    category = relationship("Category", back_populates="courses")
    speakers = relationship("CourseSpeaker", back_populates="course", cascade="all, delete-orphan")
    registrations = relationship("CourseRegistration", back_populates="course", cascade="all, delete-orphan")
    favorites = relationship("UserFavorite", back_populates="course", cascade="all, delete-orphan")
    watch_later = relationship("UserWatchLater", back_populates="course", cascade="all, delete-orphan")

class CourseSpeaker(Base):
    __tablename__ = "course_speakers"
    
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(255), nullable=False)
    bio = Column(Text, nullable=True)
    photo_url = Column(String(500), nullable=True)
    position = Column(String(255), nullable=True)
    
    course = relationship("Course", back_populates="speakers")

class UserFavorite(Base):
    __tablename__ = "user_favorites"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="favorite_courses")
    course = relationship("Course", back_populates="favorites")

class UserWatchLater(Base):
    __tablename__ = "user_watch_later"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="watch_later")
    course = relationship("Course", back_populates="watch_later")

class CourseRegistration(Base):
    __tablename__ = "course_registrations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    is_paid = Column(Boolean, default=False)
    registered_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="registrations")
    course = relationship("Course", back_populates="registrations")

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="notifications")