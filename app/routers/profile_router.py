# app/routers/profile_router.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from app import models, schemas, auth
from app.database import get_db
from app.services.encryption_service import EncryptionService
from typing import Optional, List
import os
import uuid
import shutil
import logging
from datetime import datetime, date
import json
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["Profile"])

UPLOAD_DIR = "app/static/uploads/profile"
DOCUMENTS_DIR = os.path.join(UPLOAD_DIR, "documents")

os.makedirs(DOCUMENTS_DIR, exist_ok=True)

MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.pdf'}

encryption = EncryptionService()


# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def validate_document_file(file: UploadFile) -> None:
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неподдерживаемый формат файла. Разрешены: {', '.join(ALLOWED_DOCUMENT_EXTENSIONS)}"
        )
    
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Файл слишком большой (макс. {MAX_FILE_SIZE // (1024 * 1024)}MB)"
        )
    
    try:
        import magic
        file.file.seek(0)
        mime = magic.from_buffer(file.file.read(1024), mime=True)
        file.file.seek(0)
        
        allowed_mimes = ['image/jpeg', 'image/png', 'application/pdf']
        
        if mime not in allowed_mimes:
            logger.warning(f"Файл {file.filename} имеет MIME-тип {mime}, но расширение {ext} разрешено")
    except ImportError:
        logger.warning("python-magic не установлен, проверка MIME-типа пропущена")
    except Exception as e:
        logger.warning(f"Ошибка проверки MIME-типа: {e}")


def save_file(file: UploadFile, subfolder: str = "") -> dict:
    validate_document_file(file)
    
    ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{uuid.uuid4().hex}{ext}"
    
    subfolder_path = os.path.join(DOCUMENTS_DIR, subfolder) if subfolder else DOCUMENTS_DIR
    os.makedirs(subfolder_path, exist_ok=True)
    
    filepath = os.path.join(subfolder_path, filename)
    
    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка сохранения файла: {str(e)}"
        )
    
    file_url = f"/static/uploads/profile/documents/{subfolder}/{filename}" if subfolder else f"/static/uploads/profile/documents/{filename}"
    
    return {
        "url": file_url,
        "filename": file.filename,
        "file_size": os.path.getsize(filepath),
        "file_type": ext[1:] if ext else "unknown"
    }


def delete_file(file_url: str) -> bool:
    if not file_url:
        return False
    
    relative_path = file_url.replace("/static/", "app/static/")
    if os.path.exists(relative_path):
        try:
            os.remove(relative_path)
            return True
        except Exception:
            return False
    return False


# ========== ЛИЧНЫЕ ДАННЫЕ ==========

@router.get("/personal-data")
def get_personal_data(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
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
    education = db.query(models.UserEducation).filter(
        and_(
            models.UserEducation.id == education_id,
            models.UserEducation.user_id == current_user.id
        )
    ).first()
    
    if not education:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись об образовании не найдена"
        )
    
    return schemas.EducationResponse.model_validate(education)


@router.post("/education")
def create_education(
    data: schemas.EducationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
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
    education = db.query(models.UserEducation).filter(
        and_(
            models.UserEducation.id == education_id,
            models.UserEducation.user_id == current_user.id
        )
    ).first()
    
    if not education:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись об образовании не найдена"
        )
    
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(education, key, value)
    
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
    education = db.query(models.UserEducation).filter(
        and_(
            models.UserEducation.id == education_id,
            models.UserEducation.user_id == current_user.id
        )
    ).first()
    
    if not education:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись об образовании не найдена"
        )
    
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
    education = db.query(models.UserEducation).filter(
        and_(
            models.UserEducation.id == education_id,
            models.UserEducation.user_id == current_user.id
        )
    ).first()
    
    if not education:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Запись об образовании не найдена"
        )
    
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
    work = db.query(models.UserWork).filter(
        models.UserWork.user_id == current_user.id
    ).order_by(models.UserWork.is_current.desc()).all()
    
    result = []
    for w in work:
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
    work = db.query(models.UserWork).filter(
        and_(
            models.UserWork.id == work_id,
            models.UserWork.user_id == current_user.id
        )
    ).first()
    
    if not work:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Место работы не найдено"
        )
    
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
    if not data.activity_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Вид деятельности обязателен для заполнения"
        )
    
    if not data.subjects or len(data.subjects) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Добавьте хотя бы один предмет"
        )
    
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
    work = db.query(models.UserWork).filter(
        and_(
            models.UserWork.id == work_id,
            models.UserWork.user_id == current_user.id
        )
    ).first()
    
    if not work:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Место работы не найдено"
        )
    
    update_data = data.model_dump(exclude_unset=True)
    if 'subjects' in update_data and update_data['subjects'] is not None:
        update_data['subjects'] = json.dumps(update_data['subjects'])
    
    for key, value in update_data.items():
        setattr(work, key, value)
    
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
    work = db.query(models.UserWork).filter(
        and_(
            models.UserWork.id == work_id,
            models.UserWork.user_id == current_user.id
        )
    ).first()
    
    if not work:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Место работы не найдено"
        )
    
    db.delete(work)
    db.commit()
    
    return {"message": "Место работы удалено"}


# ========== ПОЧТОВЫЙ АДРЕС ==========

@router.get("/address")
def get_address(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
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
    existing = db.query(models.UserAddress).filter(
        models.UserAddress.user_id == current_user.id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Адрес уже существует. Используйте PUT для обновления"
        )
    
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
    address = db.query(models.UserAddress).filter(
        models.UserAddress.user_id == current_user.id
    ).first()
    
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Адрес не найден"
        )
    
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(address, key, value)
    
    db.commit()
    db.refresh(address)
    
    return {"message": "Адрес обновлен"}


# ========== ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ (С ШИФРОВАНИЕМ) ==========

@router.get("/additional-info")
def get_additional_info(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        return None
    
    response_data = schemas.AdditionalInfoResponse.model_validate(info)
    response_data.snils = encryption.decrypt(info.snils) if info.snils else None
    response_data.inn = encryption.decrypt(info.inn) if info.inn else None
    
    return response_data


@router.post("/additional-info")
def create_additional_info(
    data: schemas.AdditionalInfoUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    existing = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Дополнительная информация уже существует. Используйте PUT для обновления"
        )
    
    encrypted_snils = encryption.encrypt(data.snils) if data.snils else None
    encrypted_inn = encryption.encrypt(data.inn) if data.inn else None
    
    info = models.UserAdditionalInfo(
        user_id=current_user.id,
        snils=encrypted_snils,
        passport_series=data.passport_series,
        passport_number=data.passport_number,
        passport_issued_by=data.passport_issued_by,
        passport_issued_date=data.passport_issued_date,
        passport_department_code=data.passport_department_code,
        inn=encrypted_inn,
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
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Дополнительная информация не найдена"
        )
    
    update_data = data.model_dump(exclude_unset=True)
    
    if 'snils' in update_data and update_data['snils'] is not None:
        update_data['snils'] = encryption.encrypt(update_data['snils'])
    if 'inn' in update_data and update_data['inn'] is not None:
        update_data['inn'] = encryption.encrypt(update_data['inn'])
    
    for key, value in update_data.items():
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
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Дополнительная информация не найдена. Сначала создайте запись через сохранение СНИЛС."
        )
    
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
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Дополнительная информация не найдена"
        )
    
    if info.snils_file_url:
        delete_file(info.snils_file_url)
        info.snils_file_url = None
        info.snils_file_name = None
        db.commit()
        return {"message": "Файл СНИЛС удален"}
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Файл не найден"
    )


@router.post("/upload/passport")
async def upload_passport(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Дополнительная информация не найдена. Сначала создайте запись через сохранение СНИЛС."
        )
    
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
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Дополнительная информация не найдена"
        )
    
    if info.passport_file_url:
        delete_file(info.passport_file_url)
        info.passport_file_url = None
        info.passport_file_name = None
        db.commit()
        return {"message": "Файл паспорта удален"}
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Файл не найден"
    )


@router.post("/upload/inn")
async def upload_inn(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Дополнительная информация не найдена. Сначала создайте запись через сохранение СНИЛС."
        )
    
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
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Дополнительная информация не найдена"
        )
    
    if info.inn_file_url:
        delete_file(info.inn_file_url)
        info.inn_file_url = None
        info.inn_file_name = None
        db.commit()
        return {"message": "Файл ИНН удален"}
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Файл не найден"
    )


@router.post("/upload/marriage-certificate")
async def upload_marriage_certificate(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Дополнительная информация не найдена. Сначала создайте запись через сохранение СНИЛС."
        )
    
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
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Дополнительная информация не найдена"
        )
    
    if info.marriage_certificate_file_url:
        delete_file(info.marriage_certificate_file_url)
        info.marriage_certificate_file_url = None
        info.marriage_certificate_file_name = None
        db.commit()
        return {"message": "Файл свидетельства о браке удален"}
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Файл не найден"
    )


# ========== УДАЛЕНИЕ ДОКУМЕНТОВ (ОБЩЕЕ) ==========

@router.delete("/document/{doc_type}")
async def delete_document(
    doc_type: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    if doc_type == "diploma":
        education = db.query(models.UserEducation).filter(
            and_(
                models.UserEducation.user_id == current_user.id,
                models.UserEducation.is_main == True
            )
        ).first()
        
        if not education:
            education = db.query(models.UserEducation).filter(
                models.UserEducation.user_id == current_user.id
            ).order_by(models.UserEducation.created_at.desc()).first()
        
        if not education or not education.diploma_file_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Диплом не найден"
            )
        
        file_url = education.diploma_file_url
        delete_file(file_url)
        
        education.diploma_file_url = None
        education.diploma_file_name = None
        db.commit()
        
        return {"message": "Диплом удален"}
    
    info = db.query(models.UserAdditionalInfo).filter(
        models.UserAdditionalInfo.user_id == current_user.id
    ).first()
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Дополнительная информация не найдена"
        )
    
    doc_map = {
        "passport": ("passport_file_url", "passport_file_name"),
        "inn": ("inn_file_url", "inn_file_name"),
        "marriage": ("marriage_certificate_file_url", "marriage_certificate_file_name"),
        "snils": ("snils_file_url", "snils_file_name")
    }
    
    if doc_type not in doc_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неизвестный тип документа"
        )
    
    url_field, name_field = doc_map[doc_type]
    file_url = getattr(info, url_field)
    
    if not file_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл не найден"
        )
    
    delete_file(file_url)
    setattr(info, url_field, None)
    setattr(info, name_field, None)
    db.commit()
    
    return {"message": f"Документ {doc_type} удален"}


# ========== ПОЛНЫЙ ПРОФИЛЬ (ОПТИМИЗИРОВАННЫЙ) ==========

@router.get("/full")
def get_full_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """
    Получить полный профиль пользователя.
    Оптимизировано: все связанные данные загружаются одним запросом с joinedload.
    """
    # Загружаем пользователя со всеми связанными данными одним запросом
    user = db.query(models.User).options(
        joinedload(models.User.education),
        joinedload(models.User.work),
        joinedload(models.User.address),
        joinedload(models.User.additional_info)
    ).filter(models.User.id == current_user.id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )
    
    additional_info_response = None
    if user.additional_info:
        additional_info_response = schemas.AdditionalInfoResponse.model_validate(user.additional_info)
        additional_info_response.snils = encryption.decrypt(user.additional_info.snils) if user.additional_info.snils else None
        additional_info_response.inn = encryption.decrypt(user.additional_info.inn) if user.additional_info.inn else None
    
    return schemas.FullProfileResponse(
        user=schemas.UserResponse.model_validate(user),
        personal_data=schemas.PersonalDataResponse(
            last_name=user.last_name,
            first_name=user.first_name,
            middle_name=user.middle_name,
            gender=user.gender,
            birth_date=user.birth_date,
            citizenship=user.citizenship,
            region=user.region,
            municipality=user.municipality,
            phone_raw=user.phone_raw,
            consent_to_personal_data=user.consent_to_personal_data or False
        ),
        education=[schemas.EducationResponse.model_validate(e) for e in user.education],
        work=[schemas.WorkResponse.model_validate(w) for w in user.work],
        address=schemas.AddressResponse.model_validate(user.address) if user.address else None,
        additional_info=additional_info_response,
        is_profile_complete=user.is_profile_complete()
    )


# ========== ПРОВЕРКА ЗАПОЛНЕННОСТИ ПРОФИЛЯ ==========

@router.get("/check-complete")
def check_profile_complete(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    completion_details = current_user.get_profile_completion_details()
    
    missing_fields = []
    for section in completion_details["sections"]:
        if not section["is_complete"]:
            for field in section["fields"]:
                missing_fields.append(field)
    
    if completion_details["is_complete"]:
        message = "Профиль заполнен полностью"
    else:
        incomplete_sections = [s["label"] for s in completion_details["sections"] if not s["is_complete"]]
        message = f"Не заполнены: {', '.join(incomplete_sections)}"
    
    return {
        "is_complete": completion_details["is_complete"],
        "missing_fields": missing_fields,
        "message": message,
        "sections": completion_details["sections"],
        "total_sections": completion_details["total_sections"],
        "completed_sections": completion_details["completed_sections"]
    }