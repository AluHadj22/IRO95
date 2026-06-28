# app/schemas.py
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional, List, Any, Union
from enum import Enum


class UserRole(str, Enum):
    TEACHER = "teacher"
    ADMIN = "admin"


class ModuleType(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"


class AssignmentType(str, Enum):
    TEXT = "text"
    FILE = "file"
    CHOICE = "choice"
    MULTIPLE = "multiple"
    MATCHING = "matching"
    ORDERING = "ordering"


class LessonLectureType(str, Enum):
    VIDEO = "video"
    FILE = "file"
    HYBRID = "hybrid"


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
    price: float = 0.0
    max_participants: int = 100
    format_type: str = "online"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_open_ended: bool = False
    moodle_course_id: Optional[int] = None  # ✅ ДОБАВЛЕНО!
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
    moodle_course_id: Optional[int] = None  # ✅ ДОБАВЛЕНО!


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
    moodle_course_id: Optional[int] = None  # ✅ ДОБАВЛЕНО!
    speakers: List[SpeakerResponse] = []
    is_favorite: bool = False
    is_watch_later: bool = False
    
    class Config:
        from_attributes = True


# ========== ОПЛАТА ==========

class PaymentRequest(BaseModel):
    course_id: int


class PaymentResponse(BaseModel):
    success: bool
    message: str
    payment_id: Optional[str] = None


# ========== УВЕДОМЛЕНИЯ ==========

class NotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# ========== LMS - ВЛОЖЕНИЯ ==========

class LessonAttachmentCreate(BaseModel):
    lesson_id: int
    is_required: bool = False


class LessonAttachmentResponse(BaseModel):
    id: int
    filename: str
    file_url: str
    file_size: int
    file_type: Optional[str]
    is_required: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# ========== LMS - ВОПРОСЫ ==========

class AssignmentQuestionCreate(BaseModel):
    question_text: str
    question_image: Optional[str] = None
    question_video: Optional[str] = None
    question_type: AssignmentType = AssignmentType.TEXT
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    points: int = 10
    order_index: int = 0
    is_required: bool = True
    hint: Optional[str] = None
    explanation: Optional[str] = None


class AssignmentQuestionResponse(BaseModel):
    id: int
    question_text: str
    question_image: Optional[str]
    question_video: Optional[str]
    question_type: AssignmentType
    options: Optional[List[str]]
    correct_answer: Optional[str]
    points: int
    order_index: int
    is_required: bool
    hint: Optional[str]
    explanation: Optional[str]
    
    class Config:
        from_attributes = True


class AssignmentQuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    question_image: Optional[str] = None
    question_video: Optional[str] = None
    question_type: Optional[AssignmentType] = None
    options: Optional[List[str]] = None
    correct_answer: Optional[str] = None
    points: Optional[int] = None
    order_index: Optional[int] = None
    is_required: Optional[bool] = None
    hint: Optional[str] = None
    explanation: Optional[str] = None


# ========== LMS - ЗАДАНИЯ ==========

class LessonAssignmentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assignment_type: AssignmentType = AssignmentType.TEXT
    max_score: int = 100
    passing_score: int = 60
    time_limit_minutes: int = 0
    show_timer: bool = True
    max_attempts: int = 1
    deadline: Optional[datetime] = None
    allow_retake: bool = True
    retake_count: int = 3
    auto_grade: bool = False
    questions: List[AssignmentQuestionCreate] = []


class LessonAssignmentResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    assignment_type: AssignmentType
    max_score: int
    passing_score: int
    time_limit_minutes: int
    show_timer: bool
    max_attempts: int
    created_at: datetime
    deadline: Optional[datetime]
    allow_retake: bool
    retake_count: int
    auto_grade: bool
    questions: List[AssignmentQuestionResponse] = []
    
    class Config:
        from_attributes = True


class LessonAssignmentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignment_type: Optional[AssignmentType] = None
    max_score: Optional[int] = None
    passing_score: Optional[int] = None
    time_limit_minutes: Optional[int] = None
    show_timer: Optional[bool] = None
    max_attempts: Optional[int] = None
    deadline: Optional[datetime] = None
    allow_retake: Optional[bool] = None
    retake_count: Optional[int] = None
    auto_grade: Optional[bool] = None


# ========== LMS - УРОКИ ==========

class LessonCreate(BaseModel):
    title: str
    content: Optional[str] = None
    video_url: Optional[str] = None
    order_index: int = 0
    is_free: bool = False
    duration_minutes: int = 0
    lecture_type: LessonLectureType = LessonLectureType.VIDEO
    allow_retake: bool = True
    deadline: Optional[datetime] = None
    is_published: bool = True
    lecture_file: Optional[Any] = None


class LessonResponse(BaseModel):
    id: int
    title: str
    content: Optional[str]
    video_url: Optional[str]
    order_index: int
    is_free: bool
    duration_minutes: int
    created_at: datetime
    attachments: List[LessonAttachmentResponse] = []
    assignment: Optional[LessonAssignmentResponse] = None
    is_completed: bool = False
    has_assignment: bool = False
    prev_lesson_id: Optional[int] = None
    next_lesson_id: Optional[int] = None
    lecture_type: LessonLectureType
    lecture_file_url: Optional[str] = None
    lecture_file_name: Optional[str] = None
    lecture_file_type: Optional[str] = None
    lecture_file_size: int = 0
    has_lecture_file: bool = False
    allow_retake: bool = True
    deadline: Optional[datetime] = None
    is_published: bool = True
    
    class Config:
        from_attributes = True


class LessonUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    video_url: Optional[str] = None
    order_index: Optional[int] = None
    is_free: Optional[bool] = None
    duration_minutes: Optional[int] = None
    lecture_type: Optional[LessonLectureType] = None
    allow_retake: Optional[bool] = None
    deadline: Optional[datetime] = None
    is_published: Optional[bool] = None


# ========== LMS - МОДУЛИ ==========

class ModuleCreate(BaseModel):
    title: str
    description: Optional[str] = None
    module_type: ModuleType = ModuleType.ONLINE
    order_index: int = 0


class ModuleResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    module_type: ModuleType
    order_index: int
    created_at: datetime
    lessons: List[LessonResponse] = []
    is_completed: bool = False
    lessons_count: int = 0
    completed_lessons_count: int = 0
    
    class Config:
        from_attributes = True


class ModuleUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    module_type: Optional[ModuleType] = None
    order_index: Optional[int] = None


# ========== LMS - ПРОГРЕСС ==========

class LessonProgressUpdate(BaseModel):
    lesson_id: int
    is_completed: bool = False
    last_position: int = 0
    video_watched_percent: int = 0
    time_spent_seconds: int = 0


class VideoProgressUpdate(BaseModel):
    position_seconds: int = Field(..., ge=0)
    total_duration: int = Field(..., ge=1)


class ModuleProgressResponse(BaseModel):
    module_id: int
    module_title: str
    is_completed: bool
    completed_by_teacher: bool
    completed_at: Optional[datetime]
    teacher_comment: Optional[str]
    lessons_total: int
    lessons_completed: int
    progress_percent: int


class CourseProgressResponse(BaseModel):
    course_id: int
    course_title: str
    modules: List[ModuleProgressResponse]
    total_lessons: int
    completed_lessons: int
    progress_percent: int
    is_completed: bool
    started_at: datetime
    completed_at: Optional[datetime]


# ========== LMS - ОТВЕТЫ (СУБМИССИИ) ==========

class UserAnswerCreate(BaseModel):
    question_id: int
    answer_text: Optional[str] = None
    answer_file: Optional[str] = None


class AssignmentSubmit(BaseModel):
    answers: List[UserAnswerCreate]
    is_retake: bool = False
    previous_submission_id: Optional[int] = None
    time_spent_seconds: int = 0


class QuestionFileAnswerCreate(BaseModel):
    question_id: int


class QuestionFileAnswerResponse(BaseModel):
    id: int
    question_id: int
    filename: str
    file_url: str
    file_size: int
    file_type: Optional[str]
    uploaded_at: datetime
    
    class Config:
        from_attributes = True


class UserAnswerResponse(BaseModel):
    id: int
    question_id: int
    answer_text: Optional[str]
    answer_file: Optional[str]
    is_correct: Optional[bool]
    points_earned: int
    question_text: Optional[str] = None
    question_type: Optional[AssignmentType] = None
    max_points: Optional[int] = None
    teacher_comment: Optional[str] = None
    auto_graded: bool = False
    
    class Config:
        from_attributes = True


class AssignmentSubmissionResponse(BaseModel):
    id: int
    assignment_id: int
    assignment_title: Optional[str] = None
    score: Optional[int]
    is_passed: bool
    submitted_at: datetime
    graded_by: Optional[int]
    graded_at: Optional[datetime]
    teacher_comment: Optional[str]
    current_attempt: int
    is_latest: bool
    is_retake: bool = False
    retake_number: int = 0
    previous_submission_id: Optional[int] = None
    time_spent_seconds: int = 0
    is_auto_graded: bool = False
    auto_grade_score: Optional[int] = None
    can_retake: bool = True
    answers: List[UserAnswerResponse] = []
    file_answers: List[QuestionFileAnswerResponse] = []
    
    class Config:
        from_attributes = True


class AssignmentSubmissionDetailResponse(BaseModel):
    submission_id: int
    student_name: str
    student_email: str
    course_title: str
    module_title: str
    lesson_title: str
    assignment_title: str
    submitted_at: datetime
    score: Optional[int]
    max_score: int
    is_passed: bool
    graded_by: Optional[int]
    graded_at: Optional[datetime]
    teacher_comment: Optional[str]
    is_retake: bool = False
    retake_number: int = 0
    previous_submission_id: Optional[int] = None
    time_spent_seconds: int = 0
    can_retake: bool = True
    answers: List[UserAnswerResponse]
    
    class Config:
        from_attributes = True


# ========== LMS - ПОПЫТКИ ==========

class AssignmentAttemptResponse(BaseModel):
    id: int
    attempt_number: int
    started_at: datetime
    completed_at: Optional[datetime]
    score: Optional[int]
    is_passed: bool
    is_retake: bool = False
    time_spent_seconds: int = 0
    
    class Config:
        from_attributes = True


# ========== LMS - ОЦЕНКА ОТВЕТОВ ==========

class GradeTextAnswer(BaseModel):
    submission_id: int
    question_id: int
    status: str
    points: int = 0
    comment: str = ""


class GradeMultipleChoiceAnswer(BaseModel):
    submission_id: int
    question_id: int
    selected_options: List[int]


# ========== LMS - ПЕРЕСДАЧА ==========

class RetakeRequest(BaseModel):
    lesson_id: int
    reset_progress: bool = True


class RetakeResponse(BaseModel):
    message: str
    new_submission_id: Optional[int] = None
    remaining_attempts: int
    max_attempts: int
    allow_retake: bool = True


# ========== LMS - СТАТИСТИКА ==========

class StudentStatistics(BaseModel):
    user_id: int
    full_name: str
    email: str
    total_courses: int
    completed_courses: int
    in_progress_courses: int
    total_assignments: int
    passed_assignments: int
    average_score: float
    total_lessons_completed: int
    total_hours_spent: float


class CourseStatistics(BaseModel):
    course_id: int
    course_title: str
    total_students: int
    active_students: int
    completed_students: int
    average_progress: float
    total_assignments: int
    average_score: float
    completion_rate: float


# ========== LMS - ЖУРНАЛ УЧИТЕЛЯ ==========

class TeacherJournalStudent(BaseModel):
    user_id: int
    full_name: str
    email: str
    position: Optional[str]
    organization: Optional[str]
    modules: List[dict]
    total_progress: int
    is_completed: bool
    retake_count: int = 0


class TeacherJournalResponse(BaseModel):
    course: dict
    modules: List[dict]
    students: List[TeacherJournalStudent]


# ========== LMS - ФИЛЬТРЫ ДЛЯ ПОИСКА ==========

class AssignmentFilter(BaseModel):
    course_id: Optional[int] = None
    module_id: Optional[int] = None
    lesson_id: Optional[int] = None
    user_id: Optional[int] = None
    status: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    search: Optional[str] = None


# ========== LMS - ЭКСПОРТ ==========

class ExportResult(BaseModel):
    course_id: int
    course_title: str
    students: List[dict]
    total_students: int
    export_date: datetime
    format: str = "excel"