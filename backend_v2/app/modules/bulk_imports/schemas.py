"""Schemas for academic CSV/XLSX bulk imports."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class BulkImportEntity(StrEnum):
    CLASSROOMS = "classrooms"
    SUBJECTS = "subjects"
    TEACHER_PROFILES = "teacher-profiles"
    STUDENT_PROFILES = "student-profiles"


class BulkImportRowError(BaseModel):
    row_number: int = Field(..., ge=2)
    code: str
    message: str


class BulkImportResult(BaseModel):
    entity: BulkImportEntity
    success: bool
    total_rows: int = Field(..., ge=0)
    imported_count: int = Field(..., ge=0)
    failed_count: int = Field(..., ge=0)
    errors: list[BulkImportRowError]
