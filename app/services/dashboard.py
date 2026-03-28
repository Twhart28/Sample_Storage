from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from app.repositories import storage as storage_repository
from app.schemas import SampleSearchQuery
from app.services import samples as sample_service


def build_dashboard(db: Session) -> dict:
    all_samples = sample_service.search_samples(db, SampleSearchQuery(sort="updated_at"))
    study_role_counts = dict(Counter(sample.study_role for sample in all_samples))
    custody_counts = dict(Counter(sample.custody_label for sample in all_samples))
    usage_counts = dict(Counter(sample.usage_label for sample in all_samples))
    return {
        "recent_samples": all_samples[:8],
        "study_role_counts": study_role_counts,
        "custody_counts": custody_counts,
        "usage_counts": usage_counts,
        "freezer_counts": storage_repository.occupancy_by_freezer(db),
        "unplaced_count": sum(1 for sample in all_samples if sample.custody_label == "unplaced"),
        "total_samples": len(all_samples),
    }
