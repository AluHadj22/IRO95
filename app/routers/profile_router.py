# app/routers/profile_router.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app import models, schemas, auth
from app.database import get_db
from typing import Optional, List
import os
import uuid
import shutil
from datetime import datetime, date
import json
import re

router = APIRouter(prefix="/api/profile", tags=["Profile"])

# Создаём папки для загрузки документов
UPLOAD_DIR = "app/static/uploads/profile"
DOCUMENTS_DIR = os.path.join(UPLOAD_DIR, "documents")

os.makedirs(DOCUMENTS_DIR, exist_ok=True)

# Максимальный размер файла - 20MB
MAX_FILE_SIZE = 20 * 1024 * 1024


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def save_file(file: UploadFile, subfolder: str = "") -> dict:
    """Сохраняет загруженный файл и возвращает информацию о нём"""
    allowed_extensions = ['.png', '.jpg', '.jpeg', '.pdf']
    ext = os.path.splitext(file.filename)[1].lower()
    
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемый формат файла. Разрешены: {', '.join(allowed_extensions)}")
    
    # Проверка размера файла (макс. 20MB)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"Файл слишком большой (макс. {MAX_FILE_SIZE // (1024 * 1024)}MB)")
    
    filename = f"{uuid.uuid4().hex}{ext}"
    subfolder_path = os.path.join(DOCUMENTS_DIR, subfolder) if subfolder else DOCUMENTS_DIR
    os.makedirs(subfolder_path, exist_ok=True)
    
    filepath = os.path.join(subfolder_path, filename)
    
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    file_url = f"/static/uploads/profile/documents/{subfolder}/{filename}" if subfolder else f"/static/uploads/profile/documents/{filename}"
    
    return {
        "url": file_url,
        "filename": file.filename,
        "file_size": file_size,
        "file_type": ext[1:] if ext else "unknown"
    }


def delete_file(file_url: str):
    """Удаляет файл по URL"""
    if not file_url:
        return
    
    # Извлекаем путь из URL
    relative_path = file_url.replace("/static/", "app/static/")
    if os.path.exists(relative_path):
        os.remove(relative_path)
        return True
    return False


# ========== ЛИЧНЫЕ ДАННЫЕ ==========

@router.get("/personal-data")
def get_personal_data(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить личные данные пользователя"""
    return schemas.PersonalDataResponse(
        last_name=current_user.last_name,
        first_name=current_user.first_name,
        middle_name=current_user.middle_name,
        gender=current_user.gender,
        birth_date=current_user.birth_date,
        citizenship=current_user.citizenship,
        region=current_user.region,
        municipality=current_user.municipality,
        phone_raw=current_user.phone_raw,
        consent_to_personal_data=current_user.consent_to_personal_data or False
    )


@router.put("/personal-data")
def update_personal_data(
    data: schemas.PersonalDataUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Обновить личные данные пользователя"""
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(current_user, key, value)
    
    db.commit()
    db.refresh(current_user)
    
    return {"message": "Личные данные обновлены"}


# ========== ОБРАЗОВАНИЕ ==========

@router.get("/education")
def get_education(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить данные об образовании пользователя"""
    education = db.query(models.UserEducation).filter(
        models.UserEducation.user_id == current_user.id
    ).order_by(models.UserEducation.is_main.desc()).all()
    
    return [schemas.EducationResponse.model_validate(e) for e in education]


@router.get("/education/{education_id}")
def get_education_item(
    education_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить запись об образовании по ID"""
    education = db.query(models.UserEducation).filter(
        and_(
            models.UserEducation.id == education_id,
            models.UserEducation.user_id == current_user.id
        )
    ).first()
    
    if not education:
        raise HTTPException(status_code=404, detail="Запись об образовании не найдена")
    
    return schemas.EducationResponse.model_validate(education)


@router.post("/education")
def create_education(
    data: schemas.EducationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Добавить запись об образовании"""
    education = models.UserEducation(
        user_id=current_user.id,
        education_level=data.education_level,
        document_series=data.document_series,
        registration_number=data.registration_number,
        qualification=data.qualification,
        document_number=data.document_number,
        issue_date=data.issue_date,
        academic_degree=data.academic_degree,
        academic_title=data.academic_title,
        diploma_last_name=data.diploma_last_name,
        diploma_first_name=data.diploma_first_name,
        diploma_middle_name=data.diploma_middle_name,
        is_main=data.is_main
    )
    
    # Если это основное образование, сбрасываем флаг у других
    if data.is_main:
        db.query(models.UserEducation).filter(
            models.UserEducation.user_id == current_user.id,
            models.UserEducation.is_main == True
        ).update({"is_main": False})
    
    db.add(education)
    db.commit()
    db.refresh(education)
    
    return {"message": "Образование добавлено", "id": education.id}


@router.put("/education/{education_id}")
def update_education(
    education_id: int,
    data: schemas.EducationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Обновить запись об образовании"""
    education = db.query(models.UserEducation).filter(
        and_(
            models.UserEducation.id == education_id,
            models.UserEducation.user_id == current_user.id
        )
    ).first()
    
    if not education:
        raise HTTPException(status_code=404, detail="Запись об образовании не найдена")
    
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(education, key, value)
    
    # Если это основное образование, сбрасываем флаг у других
    if data.is_main:
        db.query(models.UserEducation).filter(
            models.UserEducation.user_id == current_user.id,
            models.UserEducation.id != education_id,
            models.UserEducation.is_main == True
        ).update({"is_main": False})
    
    db.commit()
    db.refresh(education)
    
    return {"message": "Образование обновлено"}


@router.delete("/education/{education_id}")
def delete_education(
    education_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Удалить запись об образовании"""
    education = db.query(models.UserEducation).filter(
        and_(
            models.UserEducation.id == education_id,
            models.UserEducation.user_id == current_user.id
        )
    ).first()
    
    if not education:
        raise HTTPException(status_code=404, detail="Запись об образовании не найдена")
    
    # Удаляем файл диплома, если есть
    if education.diploma_file_url:
        delete_file(education.diploma_file_url)
    
    db.delete(education)
    db.commit()
    
    return {"message": "Образование удалено"}


@router.post("/education/{education_id}/upload-diploma")
async def upload_diploma(
    education_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Загрузить копию диплома"""
    education = db.query(models.UserEducation).filter(
        and_(
            models.UserEducation.id == education_id,
            models.UserEducation.user_id == current_user.id
        )
    ).first()
    
    if not education:
        raise HTTPException(status_code=404, detail="Запись об образовании не найдена")
    
    # Удаляем старый файл, если есть
    if education.diploma_file_url:
        delete_file(education.diploma_file_url)
    
    result = save_file(file, "diplomas")
    
    education.diploma_file_url = result["url"]
    education.diploma_file_name = result["filename"]
    
    db.commit()
    
    return schemas.FileUploadResponse(
        url=result["url"],
        filename=result["filename"],
        file_size=result["file_size"],
        file_type=result["file_type"],
        message="Диплом загружен"
    )


# ========== РАБОТА ==========

@router.get("/work")
def get_work(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить данные о работе пользователя"""
    work = db.query(models.UserWork).filter(
        models.UserWork.user_id == current_user.id
    ).order_by(models.UserWork.is_current.desc()).all()
    
    result = []
    for w in work:
        # Парсим subjects из JSON
        subjects = []
        if w.subjects:
            try:
                subjects = json.loads(w.subjects)
            except:
                pass
        
        result.append(schemas.WorkResponse(
            id=w.id,
            user_id=w.user_id,
            organization=w.organization,
            organization_inn=w.organization_inn,
            work_experience_years=w.work_experience_years,
            teaching_experience_years=w.teaching_experience_years,
            organization_type=w.organization_type,
            position=w.position,
            activity_type=w.activity_type,
            civil_service_status=w.civil_service_status,
            subjects=subjects,
            is_urban=w.is_urban,
            is_rural=w.is_rural,
            is_shnor=w.is_shnor,
            is_current=w.is_current,
            work_start_date=w.work_start_date,
            work_end_date=w.work_end_date,
            created_at=w.created_at,
            updated_at=w.updated_at
        ))
    
    return result


@router.get("/work/{work_id}")
def get_work_item(
    work_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить запись о работе по ID"""
    work = db.query(models.UserWork).filter(
        and_(
            models.UserWork.id == work_id,
            models.UserWork.user_id == current_user.id
        )
    ).first()
    
    if not work:
        raise HTTPException(status_code=404, detail="Место работы не найдено")
    
    subjects = []
    if work.subjects:
        try:
            subjects = json.loads(work.subjects)
        except:
            pass
    
    return schemas.WorkResponse(
        id=work.id,
        user_id=work.user_id,
        organization=work.organization,
        organization_inn=work.organization_inn,
        work_experience_years=work.work_experience_years,
        teaching_experience_years=work.teaching_experience_years,
        organization_type=work.organization_type,
        position=work.position,
        activity_type=work.activity_type,
        civil_service_status=work.civil_service_status,
        subjects=subjects,
        is_urban=work.is_urban,
        is_rural=work.is_rural,
        is_shnor=work.is_shnor,
        is_current=work.is_current,
        work_start_date=work.work_start_date,
        work_end_date=work.work_end_date,
        created_at=work.created_at,
        updated_at=work.updated_at
    )


@router.post("/work")
def create_work(
    data: schemas.WorkCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Добавить место работы"""
    # Проверка обязательных полей (на всякий случай, хотя валидация уже есть в схеме)
    if not data.activity_type:
        raise HTTPException(status_code=400, detail="Вид деятельности обязателен для заполнения")
    
    if not data.subjects or len(data.subjects) == 0:
        raise HTTPException(status_code=400, detail="Добавьте хотя бы один предмет")
    
    subjects_json = json.dumps(data.subjects) if data.subjects else None
    
    work = models.UserWork(
        user_id=current_user.id,
        organization=data.organization,
        organization_inn=data.organization_inn,
        work_experience_years=data.work_experience_years,
        teaching_experience_years=data.teaching_experience_years,
        organization_type=data.organization_type,
        position=data.position,
        activity_type=data.activity_type,
        civil_service_status=data.civil_service_status,
        subjects=subjects_json,
        is_urban=data.is_urban,
        is_rural=data.is_rural,
        is_shnor=data.is_shnor,
        is_current=data.is_current,
        work_start_date=data.work_start_date,
        work_end_date=data.work_end_date
    )
    
    # Если это текущее место работы, сбрасываем флаг у других
    if data.is_current:
        db.query(models.UserWork).filter(
            models.UserWork.user_id == current_user.id,
            models.UserWork.is_current == True
        ).update({"is_current": False})
    
    db.add(work)
    db.commit()
    db.refresh(work)
    
    return {"message": "Место работы добавлено", "id": work.id}


@router.put("/work/{work_id}")
def update_work(
    work_id: int,
    data: schemas.WorkUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Обновить место работы"""
    work = db.query(models.UserWork).filter(
        and_(
            models.UserWork.id == work_id,
            models.UserWork.user_id == current_user.id
        )
    ).first()
    
    if not work:
        raise HTTPException(status_code=404, detail="Место работы не найдено")
    
    update_data = data.model_dump(exclude_unset=True)
    if 'subjects' in update_data and update_data['subjects'] is not None:
        update_data['subjects'] = json.dumps(update_data['subjects'])
    
    for key, value in update_data.items():
        setattr(work, key, value)
    
    # Если это текущее место работы, сбрасываем флаг у других
    if data.is_current:
        db.query(models.UserWork).filter(
            models.UserWork.user_id == current_user.id,
            models.UserWork.id != work_id,
            models.UserWork.is_current == True
        ).update({"is_current": False})
    
    db.commit()
    db.refresh(work)
    
    return {"message": "Место работы обновлено"}


@router.delete("/work/{work_id}")
def delete_work(
    work_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Удалить место работы"""
    work = db.query(models.UserWork).filter(
        and_(
            models.UserWork.id == work_id,
            models.UserWork.user_id == current_user.id
        )
    ).first()
    
    if not work:
        raise HTTPException(status_code=404, detail="Место работы не найдено")
    
    db.delete(work)
    db.commit()
    
    return {"message": "Место работы удалено"}


# ========== ПОЧТОВЫЙ АДРЕС ==========

@router.get("/address")
def get_address(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить почтовый адрес пользователя"""
    address = db.query(models.UserAddress).filter(
        models.UserAddress.user_id == current_user.id
    ).first()
    
    if not address:
        return None
    
    return schemas.AddressResponse.model_validate(address)


@router.post("/address")
def create_address(
    data: schemas.AddressCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Создать почтовый адрес"""
    # Проверяем, есть ли уже адрес
    existing = db.query(models.UserAddress).filter(
        models.UserAddress.user_id == current_user.id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Адрес уже существует. Используйте PUT для обновления")
    
    address = models.UserAddress(
        user_id=current_user.id,
        postal_index=data.postal_index,
        region=data.region,
        city=data.city,
        street=data.street,
        house=data.house,
        building=data.building,
        structure=data.structure,
        apartment=data.apartment,
        is_main=data.is_main
    )
    
    db.add(address)
    db.commit()
    db.refresh(address)
    
    return {"message": "Адрес создан", "id": address.id}


@router.put("/address")
def update_address(
    data: schemas.AddressUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Обновить почтовый адрес"""
    address = db.query(models.UserAddress).filter(
        models.UserAddress.user_id == current_user.id
    ).first()
    
    if not address:
        raise HTTPException(status_code=404, detail="Адрес не найден")
    
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(address, key, value)
    
    db.commit()
    db.refresh(address)
    
    return {"message": "Адрес обновлен"}


# ========== ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ ==========

@router.get("/additional-info")
def get_additional_info(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить дополнительную информацию пользователя"""
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        return None
    
    return schemas.AdditionalInfoResponse.model_validate(info)


@router.post("/additional-info")
def create_additional_info(
    data: schemas.AdditionalInfoUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Создать дополнительную информацию"""
    existing = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Дополнительная информация уже существует. Используйте PUT для обновления")
    
    info = models.UserAdditionalInfo(
        user_id=current_user.id,
        snils=data.snils,
        passport_series=data.passport_series,
        passport_number=data.passport_number,
        passport_issued_by=data.passport_issued_by,
        passport_issued_date=data.passport_issued_date,
        passport_department_code=data.passport_department_code,
        inn=data.inn,
        data_confirmed=data.data_confirmed or False
    )
    
    db.add(info)
    db.commit()
    db.refresh(info)
    
    return {"message": "Дополнительная информация создана", "id": info.id}


@router.put("/additional-info")
def update_additional_info(
    data: schemas.AdditionalInfoUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Обновить дополнительную информацию"""
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(status_code=404, detail="Дополнительная информация не найдена")
    
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(info, key, value)
    
    db.commit()
    db.refresh(info)
    
    return {"message": "Дополнительная информация обновлена"}


# ========== ЗАГРУЗКА ДОКУМЕНТОВ ==========

@router.post("/upload/snils")
async def upload_snils(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Загрузить копию СНИЛС"""
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(status_code=404, detail="Дополнительная информация не найдена. Сначала создайте запись через сохранение СНИЛС.")
    
    if info.snils_file_url:
        delete_file(info.snils_file_url)
    
    result = save_file(file, "snils")
    
    info.snils_file_url = result["url"]
    info.snils_file_name = result["filename"]
    
    db.commit()
    
    return schemas.FileUploadResponse(
        url=result["url"],
        filename=result["filename"],
        file_size=result["file_size"],
        file_type=result["file_type"],
        message="СНИЛС загружен"
    )


@router.delete("/upload/snils")
async def delete_snils(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Удалить копию СНИЛС"""
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(status_code=404, detail="Дополнительная информация не найдена")
    
    if info.snils_file_url:
        delete_file(info.snils_file_url)
        info.snils_file_url = None
        info.snils_file_name = None
        db.commit()
        return {"message": "Файл СНИЛС удален"}
    
    raise HTTPException(status_code=404, detail="Файл не найден")


@router.post("/upload/passport")
async def upload_passport(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Загрузить копию паспорта"""
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(status_code=404, detail="Дополнительная информация не найдена. Сначала создайте запись через сохранение СНИЛС.")
    
    if info.passport_file_url:
        delete_file(info.passport_file_url)
    
    result = save_file(file, "passports")
    
    info.passport_file_url = result["url"]
    info.passport_file_name = result["filename"]
    
    db.commit()
    
    return schemas.FileUploadResponse(
        url=result["url"],
        filename=result["filename"],
        file_size=result["file_size"],
        file_type=result["file_type"],
        message="Паспорт загружен"
    )


@router.delete("/upload/passport")
async def delete_passport(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Удалить копию паспорта"""
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(status_code=404, detail="Дополнительная информация не найдена")
    
    if info.passport_file_url:
        delete_file(info.passport_file_url)
        info.passport_file_url = None
        info.passport_file_name = None
        db.commit()
        return {"message": "Файл паспорта удален"}
    
    raise HTTPException(status_code=404, detail="Файл не найден")


@router.post("/upload/inn")
async def upload_inn(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Загрузить копию ИНН"""
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(status_code=404, detail="Дополнительная информация не найдена. Сначала создайте запись через сохранение СНИЛС.")
    
    if info.inn_file_url:
        delete_file(info.inn_file_url)
    
    result = save_file(file, "inn")
    
    info.inn_file_url = result["url"]
    info.inn_file_name = result["filename"]
    
    db.commit()
    
    return schemas.FileUploadResponse(
        url=result["url"],
        filename=result["filename"],
        file_size=result["file_size"],
        file_type=result["file_type"],
        message="ИНН загружен"
    )


@router.delete("/upload/inn")
async def delete_inn(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Удалить копию ИНН"""
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(status_code=404, detail="Дополнительная информация не найдена")
    
    if info.inn_file_url:
        delete_file(info.inn_file_url)
        info.inn_file_url = None
        info.inn_file_name = None
        db.commit()
        return {"message": "Файл ИНН удален"}
    
    raise HTTPException(status_code=404, detail="Файл не найден")


@router.post("/upload/marriage-certificate")
async def upload_marriage_certificate(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Загрузить копию свидетельства о браке"""
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(status_code=404, detail="Дополнительная информация не найдена. Сначала создайте запись через сохранение СНИЛС.")
    
    if info.marriage_certificate_file_url:
        delete_file(info.marriage_certificate_file_url)
    
    result = save_file(file, "marriage")
    
    info.marriage_certificate_file_url = result["url"]
    info.marriage_certificate_file_name = result["filename"]
    
    db.commit()
    
    return schemas.FileUploadResponse(
        url=result["url"],
        filename=result["filename"],
        file_size=result["file_size"],
        file_type=result["file_type"],
        message="Свидетельство о браке загружено"
    )


@router.delete("/upload/marriage-certificate")
async def delete_marriage_certificate(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Удалить копию свидетельства о браке"""
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(status_code=404, detail="Дополнительная информация не найдена")
    
    if info.marriage_certificate_file_url:
        delete_file(info.marriage_certificate_file_url)
        info.marriage_certificate_file_url = None
        info.marriage_certificate_file_name = None
        db.commit()
        return {"message": "Файл свидетельства о браке удален"}
    
    raise HTTPException(status_code=404, detail="Файл не найден")


# ========== УДАЛЕНИЕ ДОКУМЕНТОВ (ОБЩЕЕ) ==========

@router.delete("/document/{doc_type}")
async def delete_document(
    doc_type: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Удалить документ по типу"""
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(status_code=404, detail="Дополнительная информация не найдена")
    
    doc_map = {
        "diploma": ("diploma_file_url", "diploma_file_name"),
        "passport": ("passport_file_url", "passport_file_name"),
        "inn": ("inn_file_url", "inn_file_name"),
        "marriage": ("marriage_certificate_file_url", "marriage_certificate_file_name"),
        "snils": ("snils_file_url", "snils_file_name")
    }
    
    if doc_type not in doc_map:
        raise HTTPException(status_code=400, detail="Неизвестный тип документа")
    
    url_field, name_field = doc_map[doc_type]
    file_url = getattr(info, url_field)
    
    if not file_url:
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    delete_file(file_url)
    setattr(info, url_field, None)
    setattr(info, name_field, None)
    db.commit()
    
    return {"message": f"Документ {doc_type} удален"}


# ========== ПОЛНЫЙ ПРОФИЛЬ ==========

@router.get("/full")
def get_full_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить полный профиль пользователя"""
    education = db.query(models.UserEducation).filter(
        models.UserEducation.user_id == current_user.id
    ).all()
    
    work = db.query(models.UserWork).filter(
        models.UserWork.user_id == current_user.id
    ).all()
    
    address = db.query(models.UserAddress).filter(
        models.UserAddress.user_id == current_user.id
    ).first()
    
    additional_info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    return schemas.FullProfileResponse(
        user=schemas.UserResponse.model_validate(current_user),
        personal_data=schemas.PersonalDataResponse(
            last_name=current_user.last_name,
            first_name=current_user.first_name,
            middle_name=current_user.middle_name,
            gender=current_user.gender,
            birth_date=current_user.birth_date,
            citizenship=current_user.citizenship,
            region=current_user.region,
            municipality=current_user.municipality,
            phone_raw=current_user.phone_raw,
            consent_to_personal_data=current_user.consent_to_personal_data or False
        ),
        education=[schemas.EducationResponse.model_validate(e) for e in education],
        work=[schemas.WorkResponse.model_validate(w) for w in work],
        address=schemas.AddressResponse.model_validate(address) if address else None,
        additional_info=schemas.AdditionalInfoResponse.model_validate(additional_info) if additional_info else None,
        is_profile_complete=current_user.is_profile_complete()
    )


@router.get("/check-complete")
def check_profile_complete(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Проверить, заполнен ли профиль полностью"""
    missing_fields = []
    
    if not current_user.last_name:
        missing_fields.append("last_name")
    if not current_user.first_name:
        missing_fields.append("first_name")
    if not current_user.middle_name:
        missing_fields.append("middle_name")
    if not current_user.gender:
        missing_fields.append("gender")
    if not current_user.birth_date:
        missing_fields.append("birth_date")
    if not current_user.citizenship:
        missing_fields.append("citizenship")
    if not current_user.region:
        missing_fields.append("region")
    if not current_user.municipality:
        missing_fields.append("municipality")
    if not current_user.phone_raw:
        missing_fields.append("phone_raw")
    if not current_user.consent_to_personal_data:
        missing_fields.append("consent_to_personal_data")
    
    is_complete = len(missing_fields) == 0
    
    field_names = {
        "last_name": "Фамилия",
        "first_name": "Имя",
        "middle_name": "Отчество",
        "gender": "Пол",
        "birth_date": "Дата рождения",
        "citizenship": "Гражданство",
        "region": "Субъект РФ",
        "municipality": "Муниципалитет",
        "phone_raw": "Телефон",
        "consent_to_personal_data": "Согласие на обработку данных"
    }
    
    missing_names = [field_names.get(f, f) for f in missing_fields]
    
    return schemas.ProfileCompleteCheck(
        is_complete=is_complete,
        missing_fields=missing_fields,
        message="Профиль заполнен полностью" if is_complete else f"Не заполнены: {', '.join(missing_names)}"
    )