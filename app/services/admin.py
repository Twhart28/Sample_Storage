from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain import models
from app.repositories import samples as sample_repository
from app.schemas import SampleTypeCreate, StudyCreate


class AdminError(Exception):
    pass


def create_sample_type(db: Session, data: SampleTypeCreate) -> models.SampleType:
    existing = next((sample_type for sample_type in sample_repository.list_sample_types(db) if sample_type.name == data.name), None)
    if existing is not None:
        raise AdminError("Sample type already exists")
    sample_type = models.SampleType(name=data.name, description=data.description)
    db.add(sample_type)
    db.commit()
    db.refresh(sample_type)
    return sample_type


def list_sample_types(db: Session) -> list[models.SampleType]:
    return sample_repository.list_sample_types(db)


def count_samples_for_sample_type(db: Session, sample_type_id: int) -> int:
    return sample_repository.count_samples_for_sample_type(db, sample_type_id)


def update_sample_type(db: Session, sample_type_id: int, data: SampleTypeCreate) -> models.SampleType:
    sample_type = db.get(models.SampleType, sample_type_id)
    if sample_type is None:
        raise AdminError("Sample type was not found")
    existing = next(
        (
            item
            for item in sample_repository.list_sample_types(db)
            if item.name == data.name and item.id != sample_type_id
        ),
        None,
    )
    if existing is not None:
        raise AdminError("Sample type already exists")
    sample_type.name = data.name
    sample_type.description = data.description
    db.add(sample_type)
    db.commit()
    db.refresh(sample_type)
    return sample_type


def delete_sample_type(db: Session, sample_type_id: int) -> None:
    sample_type = db.get(models.SampleType, sample_type_id)
    if sample_type is None:
        raise AdminError("Sample type was not found")
    if sample_repository.count_samples_for_sample_type(db, sample_type_id) > 0:
        raise AdminError("Sample type cannot be deleted while samples still reference it")
    db.delete(sample_type)
    db.commit()


def create_study(db: Session, data: StudyCreate) -> models.Study:
    study_name = data.name.strip()
    if sample_repository.get_study_by_name(db, study_name) is not None:
        raise AdminError("Study already exists")
    study = models.Study(name=study_name, description=data.description)
    db.add(study)
    db.commit()
    db.refresh(study)
    return study


def list_studies(db: Session) -> list[models.Study]:
    return sample_repository.list_studies(db)


def count_samples_for_study(db: Session, study_id: int) -> int:
    return sample_repository.count_samples_for_study(db, study_id)


def update_study(db: Session, study_id: int, data: StudyCreate) -> models.Study:
    study = db.get(models.Study, study_id)
    if study is None:
        raise AdminError("Study was not found")
    study_name = data.name.strip()
    existing_by_name = sample_repository.get_study_by_name(db, study_name)
    if existing_by_name is not None and existing_by_name.id != study_id:
        raise AdminError("Study already exists")
    study.name = study_name
    study.description = data.description
    db.add(study)
    db.commit()
    db.refresh(study)
    return study


def delete_study(db: Session, study_id: int) -> None:
    study = db.get(models.Study, study_id)
    if study is None:
        raise AdminError("Study was not found")
    if sample_repository.count_samples_for_study(db, study_id) > 0:
        raise AdminError("Study cannot be deleted while samples still reference it")
    db.delete(study)
    db.commit()
