"""
Pydantic validation models for the Climbing Training Tracker's Supabase
rows, plus the PipelineConfig constants they depend on.
"""

from datetime import date as dt_date, datetime
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, ValidationError, field_validator


class PipelineConfig:
    """Central place for every constant the pipeline depends on"""

    SESSIONS_TABLE = 'climbing_training'
    EXERCISES_TABLE = 'exercise'
    JUNCTION_TABLE = 'training_exercises'
    EXERCISE_CATEGORIES_TABLE = 'exercise_categories'

    ALLOWED_CATEGORIES = ['Strength', 'Stamina', 'Technique', 'Free', 'Rest']
    ALLOWED_EXERCISE_CATEGORIES = ['Strength', 'Stamina', 'Technique', 'Free']
    ALLOWED_EXERCISE_TYPES = ['Reps', 'Time']
    ALLOWED_PHASES = ['Before', 'During', 'After']

    # Ordinal encodings used for plotting progression over time
    MOONBOARD_MAPPING = {
        'V0': 0, 'V1': 0, 'V2': 1, 'V3': 2, 'V4': 3,
        'V5': 4, 'V6': 5, 'V7': 6, 'V8': 7, 'V9': 8,
        'V10': 9, 'V11': 10, 'V12': 11, 'V13': 12,
        'V14': 13, 'V15': 14, 'V16': 15, 'V17': 16
    }

    GYM_MAPPING = {
        'White': 0, 'Yellow': 1, 'Green': 2, 'Blue': 3,
        'Red': 4, 'Purple': 5, 'Black': 6
    }


# ============================================================
# Validation models
#
# Supabase's REST API returns already-typed JSON rather than raw spreadsheet
# text, so these are lighter. What's still worth validating: date parsing
# and membership checks (category/grade/type/phase).
# ============================================================

def _validate_membership(v, allowed, label: str):
    """Blank/None passes through as None; anything else must be a member
    of `allowed` (a mapping's keys or a list) or raises. Shared by every
    category/grade/type/phase field across this module and user_profile's."""
    if v is None or str(v).strip() == '':
        return None
    v = str(v).strip()
    if v not in allowed:
        raise ValueError(f'Unknown {label}: {v!r}')
    return v


def _require_nonblank_string(v, label: str) -> str:
    """Strips and requires a non-blank string, or raises."""
    if v is None or str(v).strip() == '':
        raise ValueError(f'{label} is required')
    return str(v).strip()


class SessionRecord(BaseModel):
    """A single validated row from 'climbing_training', plus a synthesized
    'exercises' comma-separated string assembled from the training_exercises join
    """

    id: int
    date_entry: Optional[datetime] = None
    date: dt_date
    category: Optional[str] = None
    effort: Optional[int] = None
    gym_grade: Optional[str] = None
    moonboard_grade: Optional[str] = None
    injured: bool = False
    exercises: Optional[str] = None
    goal_id: Optional[int] = None

    @field_validator('date_entry', mode='before')
    @classmethod
    def parse_date_entry(cls, v):
        if v is None:
            return None
        parsed = pd.to_datetime(v, errors='coerce')
        return None if pd.isna(parsed) else parsed.to_pydatetime()

    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, v):
        if v is None:
            raise ValueError('date is required')
        parsed = pd.to_datetime(v, errors='coerce')
        if pd.isna(parsed):
            raise ValueError(f'Unparseable date: {v!r}')
        return parsed.date()

    @field_validator('category', mode='before')
    @classmethod
    def validate_category(cls, v):
        return _validate_membership(v, PipelineConfig.ALLOWED_CATEGORIES, 'category')

    @field_validator('gym_grade', mode='before')
    @classmethod
    def validate_gym_grade(cls, v):
        return _validate_membership(v, PipelineConfig.GYM_MAPPING, 'gym grade')

    @field_validator('moonboard_grade', mode='before')
    @classmethod
    def validate_moonboard_grade(cls, v):
        return _validate_membership(v, PipelineConfig.MOONBOARD_MAPPING, 'moonboard grade')

    @field_validator('exercises', mode='before')
    @classmethod
    def parse_exercises(cls, v):
        if v is None or str(v).strip() == '':
            return None
        return str(v).strip()


class ExerciseRecord(BaseModel):
    """A single validated row from the 'exercise' table"""

    id: int
    name: str
    type: Optional[str] = None
    sets: Optional[int] = None
    reps: Optional[int] = None
    time: Optional[str] = None
    rest: Optional[int] = None
    comments: Optional[str] = None
    phase: Optional[str] = None
    categories: list[str] = []
    mandatory: bool = False
    exclude_from_plan: bool = False

    @field_validator('mandatory', mode='before')
    @classmethod
    def validate_mandatory(cls, v):
        return bool(v)

    @field_validator('exclude_from_plan', mode='before')
    @classmethod
    def validate_exclude_from_plan(cls, v):
        return bool(v)

    @field_validator('categories', mode='before')
    @classmethod
    def validate_categories(cls, v):
        if not v:
            return []
        cleaned = [str(c).strip() for c in v if str(c).strip()]
        invalid = [c for c in cleaned if c not in PipelineConfig.ALLOWED_EXERCISE_CATEGORIES]
        if invalid:
            raise ValueError(f'Unknown exercise categor{"y" if len(invalid) == 1 else "ies"}: {invalid!r}')
        return cleaned

    @field_validator('name', mode='before')
    @classmethod
    def name_required(cls, v):
        return _require_nonblank_string(v, 'Exercise name')

    @field_validator('type', mode='before')
    @classmethod
    def validate_type(cls, v):
        return _validate_membership(v, PipelineConfig.ALLOWED_EXERCISE_TYPES, 'exercise type')

    @field_validator('phase', mode='before')
    @classmethod
    def validate_phase(cls, v):
        return _validate_membership(v, PipelineConfig.ALLOWED_PHASES, 'phase')


def _validate_records(records: list[dict], model: type[BaseModel]) -> tuple[list[BaseModel], list[tuple[Any, str]]]:
    """Validate raw Supabase rows against a model.

    Returns (valid, errors):
        valid  - list of validated models (each already carries its own id)
        errors - list of (id, error_message) for rows that failed
    """
    valid = []
    errors = []
    for record in records:
        try:
            valid.append(model.model_validate(record))
        except ValidationError as exc:
            errors.append((record.get('id', '?'), str(exc)))
    return valid, errors
