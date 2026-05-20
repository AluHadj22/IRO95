from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app import models, schemas, auth
from app.database import get_db
from typing import Optional, List
import json
import os
import uuid
import shutil
from datetime import datetime

router = APIRouter(prefix="/api/lms", tags=["LMS"])

# Создаём папку для загрузок материалов
UPLOAD_DIR = "app/static/uploads/lms"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ========== ПОЛУЧЕНИЕ ДАННЫХ КУРСА ==========

@router.get("/courses/{course_id}/full")
def get_course_full(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    """Получить полную информацию о курсе с модулями и уроками"""
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    modules = db.query(models.CourseModule).filter(
        models.CourseModule.course_id == course_id
    ).order_by(models.CourseModule.order_index).all()
    
    result = {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "image_url": course.image_url,
        "price": course.price,
        "format_type": course.format_type,
        "modules": []
    }
    
    for module in modules:
        lessons = db.query(models.CourseLesson).filter(
            models.CourseLesson.module_id == module.id
        ).order_by(models.CourseLesson.order_index).all()
        
        module_data = {
            "id": module.id,
            "title": module.title,
            "description": module.description,
            "module_type": module.module_type,
            "order_index": module.order_index,
            "lessons": []
        }
        
        for lesson in lessons:
            is_completed = False
            if current_user:
                progress = db.query(models.UserLessonProgress).filter(
                    and_(
                        models.UserLessonProgress.user_id == current_user.id,
                        models.UserLessonProgress.lesson_id == lesson.id,
                        models.UserLessonProgress.is_completed == True
                    )
                ).first()
                is_completed = progress is not None
            
            module_data["lessons"].append({
                "id": lesson.id,
                "title": lesson.title,
                "content": lesson.content,
                "video_url": lesson.video_url,
                "is_free": lesson.is_free,
                "duration_minutes": lesson.duration_minutes,
                "has_assignment": lesson.assignment is not None,
                "is_completed": is_completed,
                "attachments": [{
                    "id": a.id,
                    "filename": a.filename,
                    "file_url": a.file_url,
                    "file_type": a.file_type
                } for a in lesson.attachments]
            })
        
        result["modules"].append(module_data)
    
    return result


@router.get("/courses/{course_id}/teacher/journal")
def get_teacher_journal(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Получить журнал успеваемости для учителя"""
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    registrations = db.query(models.CourseRegistration, models.User).join(
        models.User
    ).filter(models.CourseRegistration.course_id == course_id).all()
    
    modules = db.query(models.CourseModule).filter(
        models.CourseModule.course_id == course_id
    ).order_by(models.CourseModule.order_index).all()
    
    result = {
        "course": {"id": course.id, "title": course.title, "format_type": course.format_type},
        "modules": [{"id": m.id, "title": m.title, "type": m.module_type} for m in modules],
        "students": []
    }
    
    for reg, user in registrations:
        student_data = {
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "position": user.position,
            "organization": user.organization,
            "modules": []
        }
        
        for module in modules:
            module_progress = db.query(models.UserModuleProgress).filter(
                and_(
                    models.UserModuleProgress.user_id == user.id,
                    models.UserModuleProgress.module_id == module.id
                )
            ).first()
            
            student_data["modules"].append({
                "module_id": module.id,
                "is_completed": module_progress.is_completed if module_progress else False,
                "completed_by_teacher": module_progress.completed_by_teacher if module_progress else False,
                "completed_at": module_progress.completed_at if module_progress else None
            })
        
        result["students"].append(student_data)
    
    return result


# ========== УПРАВЛЕНИЕ МОДУЛЯМИ ==========

@router.post("/courses/{course_id}/modules")
def create_module(
    course_id: int,
    request_data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Создать модуль курса"""
    print(f"Creating module for course {course_id} with data: {request_data}")
    
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    module = models.CourseModule(
        course_id=course_id,
        title=request_data.get("title", ""),
        description=request_data.get("description", ""),
        module_type=request_data.get("module_type", "online"),
        order_index=request_data.get("order_index", 0)
    )
    db.add(module)
    db.commit()
    db.refresh(module)
    
    return {"message": "Module created", "id": module.id, "title": module.title}


@router.delete("/modules/{module_id}")
def delete_module(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Удалить модуль"""
    module = db.query(models.CourseModule).filter(models.CourseModule.id == module_id).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    
    db.delete(module)
    db.commit()
    return {"message": "Module deleted"}


# ========== УПРАВЛЕНИЕ УРОКАМИ ==========

@router.post("/modules/{module_id}/lessons")
async def create_lesson(
    module_id: int,
    request_data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Создать урок в модуле"""
    print(f"Creating lesson for module {module_id} with data: {request_data}")
    
    module = db.query(models.CourseModule).filter(models.CourseModule.id == module_id).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    
    lesson = models.CourseLesson(
        module_id=module_id,
        title=request_data.get("title", ""),
        content=request_data.get("content", ""),
        video_url=request_data.get("video_url", ""),
        is_free=request_data.get("is_free", False),
        duration_minutes=request_data.get("duration_minutes", 0),
        order_index=request_data.get("order_index", 0)
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    
    return {"message": "Lesson created", "id": lesson.id, "title": lesson.title}


@router.delete("/lessons/{lesson_id}")
def delete_lesson(
    lesson_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Удалить урок"""
    lesson = db.query(models.CourseLesson).filter(models.CourseLesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    db.delete(lesson)
    db.commit()
    return {"message": "Lesson deleted"}


@router.get("/lessons/{lesson_id}")
def get_lesson(
    lesson_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    """Получить урок с содержимым и заданием"""
    lesson = db.query(models.CourseLesson).filter(models.CourseLesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    if not lesson.is_free and not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if current_user and not lesson.is_free:
        registration = db.query(models.CourseRegistration).filter(
            and_(
                models.CourseRegistration.user_id == current_user.id,
                models.CourseRegistration.course_id == lesson.module.course_id
            )
        ).first()
        if not registration:
            raise HTTPException(status_code=403, detail="You are not registered for this course")
    
    is_completed = False
    if current_user:
        progress = db.query(models.UserLessonProgress).filter(
            and_(
                models.UserLessonProgress.user_id == current_user.id,
                models.UserLessonProgress.lesson_id == lesson_id,
                models.UserLessonProgress.is_completed == True
            )
        ).first()
        is_completed = progress is not None
    
    assignment = None
    if lesson.assignment:
        questions = db.query(models.AssignmentQuestion).filter(
            models.AssignmentQuestion.assignment_id == lesson.assignment.id
        ).order_by(models.AssignmentQuestion.order_index).all()
        
        assignment = {
            "id": lesson.assignment.id,
            "title": lesson.assignment.title,
            "description": lesson.assignment.description,
            "max_score": lesson.assignment.max_score,
            "passing_score": lesson.assignment.passing_score,
            "questions": []
        }
        
        for q in questions:
            # Парсим options если это строка JSON
            options_value = q.options
            if options_value and isinstance(options_value, str):
                try:
                    # Пробуем распарсить JSON
                    parsed = json.loads(options_value)
                    # Если распарсилось и это список - используем его
                    if isinstance(parsed, list):
                        options_value = parsed
                    # Если распарсилось и это строка - возможно двойная сериализация
                    elif isinstance(parsed, str):
                        try:
                            double_parsed = json.loads(parsed)
                            if isinstance(double_parsed, list):
                                options_value = double_parsed
                            else:
                                options_value = parsed
                        except:
                            options_value = parsed
                except:
                    # Если не парсится, оставляем как есть
                    pass
            
            assignment["questions"].append({
                "id": q.id,
                "question_text": q.question_text,
                "question_image": q.question_image,
                "question_video": q.question_video,
                "question_type": q.question_type,
                "options": options_value,
                "points": q.points
            })
    
    prev_lesson = db.query(models.CourseLesson).filter(
        models.CourseLesson.module_id == lesson.module_id,
        models.CourseLesson.order_index < lesson.order_index
    ).order_by(models.CourseLesson.order_index.desc()).first()
    
    next_lesson = db.query(models.CourseLesson).filter(
        models.CourseLesson.module_id == lesson.module_id,
        models.CourseLesson.order_index > lesson.order_index
    ).order_by(models.CourseLesson.order_index.asc()).first()
    
    return {
        "id": lesson.id,
        "title": lesson.title,
        "content": lesson.content,
        "video_url": lesson.video_url,
        "duration_minutes": lesson.duration_minutes,
        "is_free": lesson.is_free,
        "is_completed": is_completed,
        "has_assignment": lesson.assignment is not None,
        "attachments": [{
            "id": a.id,
            "filename": a.filename,
            "file_url": a.file_url,
            "file_type": a.file_type
        } for a in lesson.attachments],
        "assignment": assignment,
        "prev_lesson_id": prev_lesson.id if prev_lesson else None,
        "next_lesson_id": next_lesson.id if next_lesson else None
    }


@router.post("/lessons/{lesson_id}/complete")
def complete_lesson(
    lesson_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Отметить урок как пройденный"""
    lesson = db.query(models.CourseLesson).filter(models.CourseLesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    if lesson.assignment:
        submission = db.query(models.AssignmentSubmission).filter(
            and_(
                models.AssignmentSubmission.assignment_id == lesson.assignment.id,
                models.AssignmentSubmission.user_id == current_user.id,
                models.AssignmentSubmission.is_passed == True
            )
        ).first()
        
        if not submission:
            raise HTTPException(status_code=400, detail="Complete the assignment first")
    
    user_progress = db.query(models.UserLessonProgress).filter(
        and_(
            models.UserLessonProgress.user_id == current_user.id,
            models.UserLessonProgress.lesson_id == lesson_id
        )
    ).first()
    
    if not user_progress:
        user_progress = models.UserLessonProgress(
            user_id=current_user.id,
            lesson_id=lesson_id,
            is_completed=True,
            completed_at=datetime.utcnow()
        )
        db.add(user_progress)
    else:
        user_progress.is_completed = True
        user_progress.completed_at = datetime.utcnow()
    
    db.commit()
    
    # Проверяем модуль
    module = lesson.module
    lessons_in_module = db.query(models.CourseLesson).filter(
        models.CourseLesson.module_id == module.id
    ).all()
    
    completed_lessons = db.query(models.UserLessonProgress).filter(
        and_(
            models.UserLessonProgress.user_id == current_user.id,
            models.UserLessonProgress.lesson_id.in_([l.id for l in lessons_in_module]),
            models.UserLessonProgress.is_completed == True
        )
    ).count()
    
    if completed_lessons == len(lessons_in_module):
        module_progress = db.query(models.UserModuleProgress).filter(
            and_(
                models.UserModuleProgress.user_id == current_user.id,
                models.UserModuleProgress.module_id == module.id
            )
        ).first()
        
        if not module_progress:
            module_progress = models.UserModuleProgress(
                user_id=current_user.id,
                module_id=module.id,
                is_completed=True,
                completed_at=datetime.utcnow()
            )
            db.add(module_progress)
        else:
            module_progress.is_completed = True
            module_progress.completed_at = datetime.utcnow()
        
        db.commit()
        
        # Проверяем весь курс
        course_modules = db.query(models.CourseModule).filter(
            models.CourseModule.course_id == module.course_id
        ).all()
        
        completed_modules = db.query(models.UserModuleProgress).filter(
            and_(
                models.UserModuleProgress.user_id == current_user.id,
                models.UserModuleProgress.module_id.in_([m.id for m in course_modules]),
                models.UserModuleProgress.is_completed == True
            )
        ).count()
        
        if completed_modules == len(course_modules):
            course_progress = db.query(models.UserProgress).filter(
                and_(
                    models.UserProgress.user_id == current_user.id,
                    models.UserProgress.course_id == module.course_id
                )
            ).first()
            
            if course_progress:
                course_progress.is_completed = True
                course_progress.completed_at = datetime.utcnow()
                course_progress.progress_percent = 100
                db.commit()
    
    return {"message": "Lesson completed"}


# ========== УПРАВЛЕНИЕ ЗАДАНИЯМИ ==========

@router.post("/lessons/{lesson_id}/assignment")
def create_assignment(
    lesson_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Создать задание для урока"""
    print(f"Creating assignment for lesson {lesson_id} with data: {data}")
    
    lesson = db.query(models.CourseLesson).filter(models.CourseLesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    
    assignment = models.LessonAssignment(
        lesson_id=lesson_id,
        title=data.get("title", ""),
        description=data.get("description", ""),
        max_score=data.get("max_score", 100),
        passing_score=data.get("passing_score", 60)
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    
    return {"message": "Assignment created", "id": assignment.id}


@router.post("/assignments/{assignment_id}/questions")
def add_question(
    assignment_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Добавить вопрос в задание"""
    print(f"Adding question to assignment {assignment_id}: {data}")
    
    assignment = db.query(models.LessonAssignment).filter(
        models.LessonAssignment.id == assignment_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Обработка options - убираем двойную сериализацию
    options_raw = data.get("options", [])
    
    # Если options пришли как строка, пытаемся распарсить
    if isinstance(options_raw, str):
        try:
            options_raw = json.loads(options_raw)
        except:
            pass
    
    # Если options это список, преобразуем в JSON строку
    if isinstance(options_raw, list):
        options_value = json.dumps(options_raw)
    else:
        options_value = json.dumps([])
    
    question = models.AssignmentQuestion(
        assignment_id=assignment_id,
        question_text=data.get("question_text", ""),
        question_type=data.get("question_type", "text"),
        options=options_value,
        correct_answer=str(data.get("correct_answer", "")),
        points=data.get("points", 10),
        order_index=data.get("order_index", 0)
    )
    db.add(question)
    db.commit()
    
    return {"message": "Question added", "id": question.id}


@router.post("/assignments/{assignment_id}/submit")
def submit_assignment(
    assignment_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Отправить ответы на задание"""
    assignment = db.query(models.LessonAssignment).filter(
        models.LessonAssignment.id == assignment_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    answers_data = data.get("answers", [])
    
    submission = db.query(models.AssignmentSubmission).filter(
        and_(
            models.AssignmentSubmission.assignment_id == assignment_id,
            models.AssignmentSubmission.user_id == current_user.id
        )
    ).first()
    
    if not submission:
        submission = models.AssignmentSubmission(
            assignment_id=assignment_id,
            user_id=current_user.id
        )
        db.add(submission)
        db.flush()
    
    total_points = 0
    has_text_answers = False
    
    for ans_data in answers_data:
        question = db.query(models.AssignmentQuestion).filter(
            models.AssignmentQuestion.id == ans_data["question_id"]
        ).first()
        
        if not question:
            continue
        
        # Проверяем, есть ли уже ответ на этот вопрос
        existing_answer = db.query(models.UserAnswer).filter(
            and_(
                models.UserAnswer.submission_id == submission.id,
                models.UserAnswer.question_id == question.id
            )
        ).first()
        
        if existing_answer:
            # Если ответ уже есть, обновляем его
            existing_answer.answer_text = ans_data.get("answer", "")
            # Для текстовых ответов сбрасываем статус проверки
            if question.question_type == "text":
                existing_answer.is_correct = None
                existing_answer.points_earned = 0
                has_text_answers = True
            elif question.question_type == "choice":
                # Для вопросов с выбором сразу проверяем
                is_correct = False
                if question.correct_answer and ans_data.get("answer"):
                    try:
                        correct_idx = int(question.correct_answer)
                        user_idx = int(ans_data["answer"])
                        is_correct = user_idx == correct_idx
                    except:
                        pass
                existing_answer.is_correct = is_correct
                existing_answer.points_earned = question.points if is_correct else 0
                total_points += existing_answer.points_earned
        else:
            # Создаём новый ответ
            if question.question_type == "choice":
                is_correct = False
                if question.correct_answer and ans_data.get("answer"):
                    try:
                        correct_idx = int(question.correct_answer)
                        user_idx = int(ans_data["answer"])
                        is_correct = user_idx == correct_idx
                    except:
                        pass
                points_earned = question.points if is_correct else 0
                total_points += points_earned
                
                user_answer = models.UserAnswer(
                    submission_id=submission.id,
                    question_id=question.id,
                    answer_text=ans_data.get("answer", ""),
                    is_correct=is_correct,
                    points_earned=points_earned
                )
                db.add(user_answer)
            else:  # text question
                has_text_answers = True
                user_answer = models.UserAnswer(
                    submission_id=submission.id,
                    question_id=question.id,
                    answer_text=ans_data.get("answer", ""),
                    is_correct=None,  # Ожидает проверки учителя
                    points_earned=0
                )
                db.add(user_answer)
    
    # Обновляем общий балл только для автоматически проверяемых вопросов
    submission.score = total_points
    
    # Задание считается пройденным ТОЛЬКО если нет текстовых вопросов И сумма баллов >= проходного
    if not has_text_answers:
        submission.is_passed = total_points >= assignment.passing_score
    else:
        # Если есть текстовые вопросы, задание не считается пройденным до проверки учителем
        submission.is_passed = False
    
    # Сбрасываем graded_by, так как появились новые ответы
    submission.graded_by = None
    submission.graded_at = None
    
    db.commit()
    
    # Создаём уведомление для учителя (если есть текстовые ответы)
    if has_text_answers:
        # Находим всех админов/учителей курса
        lesson = assignment.lesson
        course = lesson.module.course
        admins = db.query(models.User).filter(models.User.role == models.UserRole.ADMIN).all()
        
        for admin in admins:
            notification = models.Notification(
                user_id=admin.id,
                title="Новые ответы на проверку",
                message=f"Студент {current_user.full_name} отправил ответы на задание \"{assignment.title}\" в курсе \"{course.title}\". Требуется проверка."
            )
            db.add(notification)
        db.commit()
    
    # Определяем сообщение для пользователя
    if has_text_answers:
        message = "Ответы отправлены на проверку учителю. После проверки вы сможете завершить урок."
    else:
        if submission.is_passed:
            message = "Задание пройдено! Теперь вы можете завершить урок."
        else:
            message = f"Задание не пройдено. Набрано {total_points} из {assignment.passing_score} баллов. Попробуйте ещё раз."
    
    return {
        "message": message,
        "score": total_points,
        "max_score": assignment.max_score,
        "passed": submission.is_passed,
        "has_text_answers": has_text_answers
    }


# ========== УЧИТЕЛЬСКИЙ ЖУРНАЛ ==========

@router.post("/teacher/mark-module-completed")
def mark_module_completed(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Отметить модуль как пройденный для студента"""
    print(f"Marking module completed: {data}")
    
    user_id = data.get("user_id")
    module_id = data.get("module_id")
    comment = data.get("comment", "")
    
    module = db.query(models.CourseModule).filter(models.CourseModule.id == module_id).first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    
    module_progress = db.query(models.UserModuleProgress).filter(
        and_(
            models.UserModuleProgress.user_id == user_id,
            models.UserModuleProgress.module_id == module_id
        )
    ).first()
    
    if not module_progress:
        module_progress = models.UserModuleProgress(
            user_id=user_id,
            module_id=module_id,
            is_completed=True,
            completed_by_teacher=True,
            completed_at=datetime.utcnow(),
            teacher_comment=comment
        )
        db.add(module_progress)
    else:
        module_progress.is_completed = True
        module_progress.completed_by_teacher = True
        module_progress.completed_at = datetime.utcnow()
        module_progress.teacher_comment = comment
    
    db.commit()
    
    # Проверяем, все ли модули пройдены
    course_modules = db.query(models.CourseModule).filter(
        models.CourseModule.course_id == module.course_id
    ).all()
    
    completed_modules = db.query(models.UserModuleProgress).filter(
        and_(
            models.UserModuleProgress.user_id == user_id,
            models.UserModuleProgress.module_id.in_([m.id for m in course_modules]),
            models.UserModuleProgress.is_completed == True
        )
    ).count()
    
    if completed_modules == len(course_modules):
        course_progress = db.query(models.UserProgress).filter(
            and_(
                models.UserProgress.user_id == user_id,
                models.UserProgress.course_id == module.course_id
            )
        ).first()
        
        if course_progress:
            course_progress.is_completed = True
            course_progress.completed_at = datetime.utcnow()
            course_progress.progress_percent = 100
            db.commit()
    
    return {"message": "Module marked as completed"}


# ========== ЗАГРУЗКА ФАЙЛОВ ==========

@router.post("/upload-lesson-file")
async def upload_lesson_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Загрузить файл для урока"""
    ext = file.filename.split('.')[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    content = await file.read()
    with open(filepath, "wb") as buffer:
        buffer.write(content)
    
    file_url = f"/static/uploads/lms/{filename}"
    
    return {"url": file_url, "filename": file.filename, "message": "File uploaded"}


# ========== СТАТУС ТЕКСТОВЫХ ОТВЕТОВ ДЛЯ СТУДЕНТА ==========

@router.get("/assignment/{assignment_id}/status")
def get_assignment_text_answers_status(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить статус проверки текстовых ответов для текущего студента"""
    
    assignment = db.query(models.LessonAssignment).filter(
        models.LessonAssignment.id == assignment_id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Получаем все текстовые вопросы в задании
    text_questions = db.query(models.AssignmentQuestion).filter(
        and_(
            models.AssignmentQuestion.assignment_id == assignment_id,
            models.AssignmentQuestion.question_type == "text"
        )
    ).all()
    
    # Получаем submission студента
    submission = db.query(models.AssignmentSubmission).filter(
        and_(
            models.AssignmentSubmission.assignment_id == assignment_id,
            models.AssignmentSubmission.user_id == current_user.id
        )
    ).first()
    
    result = {}
    
    for question in text_questions:
        if not submission:
            result[str(question.id)] = None  # Нет ответа
            continue
        
        # Ищем ответ на этот вопрос
        user_answer = db.query(models.UserAnswer).filter(
            and_(
                models.UserAnswer.submission_id == submission.id,
                models.UserAnswer.question_id == question.id
            )
        ).first()
        
        if not user_answer:
            result[str(question.id)] = None  # Нет ответа
        elif user_answer.is_correct is None:
            result[str(question.id)] = "pending"  # Ожидает проверки
        elif user_answer.is_correct:
            result[str(question.id)] = "approved"  # Зачтено
        else:
            result[str(question.id)] = "rejected"  # Не зачтено
    
    return result


# ========== ПРОВЕРКА ТЕКСТОВЫХ ОТВЕТОВ (ДЛЯ УЧИТЕЛЯ) ==========

@router.get("/courses/{course_id}/submissions/pending")
def get_pending_submissions(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Получить все непроверенные текстовые ответы для курса"""
    
    # Проверяем существование курса
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Получаем все модули курса
    modules = db.query(models.CourseModule).filter(
        models.CourseModule.course_id == course_id
    ).all()
    
    module_ids = [m.id for m in modules]
    
    # Получаем все уроки этих модулей
    lessons = db.query(models.CourseLesson).filter(
        models.CourseLesson.module_id.in_(module_ids)
    ).all()
    
    lesson_ids = [l.id for l in lessons]
    
    # Получаем все задания этих уроков
    assignments = db.query(models.LessonAssignment).filter(
        models.LessonAssignment.lesson_id.in_(lesson_ids)
    ).all()
    
    assignment_ids = [a.id for a in assignments]
    
    # Получаем все вопросы с типом 'text' из этих заданий
    text_questions = db.query(models.AssignmentQuestion).filter(
        and_(
            models.AssignmentQuestion.assignment_id.in_(assignment_ids),
            models.AssignmentQuestion.question_type == "text"
        )
    ).all()
    
    # Получаем все ответы на эти вопросы, которые ещё не проверены
    pending_submissions = []
    
    for question in text_questions:
        # Получаем все ответы на этот вопрос
        answers = db.query(models.UserAnswer).filter(
            models.UserAnswer.question_id == question.id
        ).all()
        
        for answer in answers:
            # Получаем submission
            submission = db.query(models.AssignmentSubmission).filter(
                models.AssignmentSubmission.id == answer.submission_id
            ).first()
            
            # Проверяем, что ответ ещё не проверен (graded_by is None) и не зачтен/отклонен
            if submission and submission.graded_by is None and answer.is_correct is False:
                user = db.query(models.User).filter(models.User.id == submission.user_id).first()
                lesson = db.query(models.CourseLesson).filter(
                    models.CourseLesson.id == question.assignment.lesson_id
                ).first()
                
                if lesson and lesson.module.course_id == course_id:
                    pending_submissions.append({
                        "submission_id": submission.id,
                        "question_id": question.id,
                        "answer_text": answer.answer_text,
                        "student_name": user.full_name if user else "Unknown",
                        "student_email": user.email if user else "Unknown",
                        "question_text": question.question_text,
                        "course_title": course.title,
                        "lesson_title": lesson.title,
                        "points": question.points
                    })
    
    return pending_submissions


@router.post("/grade-text-answer")
def grade_text_answer(
    data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Оценить текстовый ответ студента"""
    
    submission_id = data.get("submission_id")
    question_id = data.get("question_id")
    status = data.get("status")  # "pass", "fail", "retake"
    points = data.get("points", 0)
    comment = data.get("comment", "")
    
    # Получаем submission
    submission = db.query(models.AssignmentSubmission).filter(
        models.AssignmentSubmission.id == submission_id
    ).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Получаем ответ
    user_answer = db.query(models.UserAnswer).filter(
        and_(
            models.UserAnswer.submission_id == submission_id,
            models.UserAnswer.question_id == question_id
        )
    ).first()
    
    if not user_answer:
        raise HTTPException(status_code=404, detail="Answer not found")
    
    # Получаем вопрос
    question = db.query(models.AssignmentQuestion).filter(
        models.AssignmentQuestion.id == question_id
    ).first()
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Обновляем ответ
    if status == "pass":
        user_answer.is_correct = True
        user_answer.points_earned = points
    elif status == "fail":
        user_answer.is_correct = False
        user_answer.points_earned = 0
    elif status == "retake":
        # Для пересдачи - удаляем ответ, чтобы студент мог отправить снова
        db.delete(user_answer)
        
        # Также удаляем submission если это был единственный ответ
        other_answers = db.query(models.UserAnswer).filter(
            models.UserAnswer.submission_id == submission_id
        ).count()
        
        if other_answers <= 1:
            db.delete(submission)
        
        db.commit()
        return {"message": "Answer marked for retake. Student can try again."}
    
    # Обновляем submission
    submission.graded_by = current_user.id
    submission.graded_at = datetime.utcnow()
    submission.teacher_comment = comment
    
    # Пересчитываем общий балл submission (только для вопросов с выбором варианта)
    all_answers = db.query(models.UserAnswer).filter(
        models.UserAnswer.submission_id == submission_id
    ).all()
    
    total_points = sum(a.points_earned for a in all_answers if a.is_correct is not None)
    submission.score = total_points
    submission.is_passed = total_points >= submission.assignment.passing_score
    
    # Проверяем, все ли текстовые вопросы проверены и зачтены
    text_questions = db.query(models.AssignmentQuestion).filter(
        and_(
            models.AssignmentQuestion.assignment_id == submission.assignment_id,
            models.AssignmentQuestion.question_type == "text"
        )
    ).all()
    
    all_text_questions_graded = True
    all_text_questions_passed = True
    
    for tq in text_questions:
        tq_answer = db.query(models.UserAnswer).filter(
            and_(
                models.UserAnswer.submission_id == submission_id,
                models.UserAnswer.question_id == tq.id
            )
        ).first()
        
        if not tq_answer or tq_answer.is_correct is None:
            all_text_questions_graded = False
            break
        if not tq_answer.is_correct:
            all_text_questions_passed = False
    
    # Если все текстовые вопросы проверены и зачтены, отмечаем урок как пройденный
    if all_text_questions_graded and all_text_questions_passed:
        lesson = submission.assignment.lesson
        user_progress = db.query(models.UserLessonProgress).filter(
            and_(
                models.UserLessonProgress.user_id == submission.user_id,
                models.UserLessonProgress.lesson_id == lesson.id
            )
        ).first()
        
        if not user_progress:
            user_progress = models.UserLessonProgress(
                user_id=submission.user_id,
                lesson_id=lesson.id,
                is_completed=True,
                completed_at=datetime.utcnow()
            )
            db.add(user_progress)
        elif not user_progress.is_completed:
            user_progress.is_completed = True
            user_progress.completed_at = datetime.utcnow()
        
        # Проверяем, все ли уроки в модуле пройдены
        module = lesson.module
        lessons_in_module = db.query(models.CourseLesson).filter(
            models.CourseLesson.module_id == module.id
        ).all()
        
        completed_lessons = db.query(models.UserLessonProgress).filter(
            and_(
                models.UserLessonProgress.user_id == submission.user_id,
                models.UserLessonProgress.lesson_id.in_([l.id for l in lessons_in_module]),
                models.UserLessonProgress.is_completed == True
            )
        ).count()
        
        if completed_lessons == len(lessons_in_module):
            module_progress = db.query(models.UserModuleProgress).filter(
                and_(
                    models.UserModuleProgress.user_id == submission.user_id,
                    models.UserModuleProgress.module_id == module.id
                )
            ).first()
            
            if not module_progress:
                module_progress = models.UserModuleProgress(
                    user_id=submission.user_id,
                    module_id=module.id,
                    is_completed=True,
                    completed_at=datetime.utcnow()
                )
                db.add(module_progress)
            elif not module_progress.is_completed:
                module_progress.is_completed = True
                module_progress.completed_at = datetime.utcnow()
            
            # Проверяем весь курс
            course_modules = db.query(models.CourseModule).filter(
                models.CourseModule.course_id == module.course_id
            ).all()
            
            completed_modules = db.query(models.UserModuleProgress).filter(
                and_(
                    models.UserModuleProgress.user_id == submission.user_id,
                    models.UserModuleProgress.module_id.in_([m.id for m in course_modules]),
                    models.UserModuleProgress.is_completed == True
                )
            ).count()
            
            if completed_modules == len(course_modules):
                course_progress = db.query(models.UserProgress).filter(
                    and_(
                        models.UserProgress.user_id == submission.user_id,
                        models.UserProgress.course_id == module.course_id
                    )
                ).first()
                
                if course_progress and not course_progress.is_completed:
                    course_progress.is_completed = True
                    course_progress.completed_at = datetime.utcnow()
                    course_progress.progress_percent = 100
    
    db.commit()
    
    # Создаём уведомление для студента
    notification = models.Notification(
        user_id=submission.user_id,
        title="Задание проверено",
        message=f"Ваш ответ на вопрос \"{question.question_text[:50]}...\" проверен. " + 
                (f"✅ Зачтено! Получено баллов: {points}" if status == "pass" else 
                 (f"❌ Не зачтено. {comment}" if status == "fail" else "🔄 Отправлено на пересдачу. Попробуйте ещё раз."))
    )
    db.add(notification)
    db.commit()
    
    return {
        "message": "Answer graded successfully",
        "status": status,
        "points": points if status == "pass" else 0,
        "comment": comment
    }


@router.get("/submissions/{submission_id}")
def get_submission_details(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Получить детали submission для проверки"""
    
    submission = db.query(models.AssignmentSubmission).filter(
        models.AssignmentSubmission.id == submission_id
    ).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    user = db.query(models.User).filter(models.User.id == submission.user_id).first()
    assignment = submission.assignment
    lesson = assignment.lesson
    module = lesson.module
    course = module.course
    
    # Получаем все ответы
    answers = []
    for answer in submission.answers:
        question = db.query(models.AssignmentQuestion).filter(
            models.AssignmentQuestion.id == answer.question_id
        ).first()
        
        answers.append({
            "question_id": question.id,
            "question_text": question.question_text,
            "answer_text": answer.answer_text,
            "is_correct": answer.is_correct,
            "points_earned": answer.points_earned,
            "max_points": question.points
        })
    
    return {
        "submission_id": submission.id,
        "student_name": user.full_name if user else "Unknown",
        "student_email": user.email if user else "Unknown",
        "course_title": course.title,
        "module_title": module.title,
        "lesson_title": lesson.title,
        "assignment_title": assignment.title,
        "submitted_at": submission.submitted_at,
        "score": submission.score,
        "max_score": assignment.max_score,
        "is_passed": submission.is_passed,
        "graded_by": submission.graded_by,
        "graded_at": submission.graded_at,
        "teacher_comment": submission.teacher_comment,
        "answers": answers
    }