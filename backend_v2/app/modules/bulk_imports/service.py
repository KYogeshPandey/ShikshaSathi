"""Per-row validated academic import orchestration."""

from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.modules.academics.classrooms_service import ClassroomService
from app.modules.academics.schemas import ClassroomCreate, SubjectCreate
from app.modules.academics.subjects_service import SubjectService
from app.modules.bulk_imports.errors import BulkImportFileError
from app.modules.bulk_imports.parser import parse_import_file
from app.modules.bulk_imports.schemas import (
    BulkImportEntity,
    BulkImportResult,
    BulkImportRowError,
)
from app.modules.profiles.schemas import StudentProfileCreate, TeacherProfileCreate
from app.modules.profiles.student_service import StudentProfileService
from app.modules.profiles.teacher_service import TeacherProfileService

_EXPECTED_COLUMNS: dict[BulkImportEntity, set[str]] = {
    BulkImportEntity.CLASSROOMS: {"name", "code", "grade_level", "section"},
    BulkImportEntity.SUBJECTS: {"name", "code", "is_elective"},
    BulkImportEntity.TEACHER_PROFILES: {"user_id", "employee_code", "phone_number"},
    BulkImportEntity.STUDENT_PROFILES: {"user_id", "classroom_id", "roll_number"},
}


def _validation_message(exc: ValidationError) -> str:
    messages = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error.get("loc", []))
        message = str(error.get("msg", "Invalid value."))
        messages.append(f"{field}: {message}" if field else message)
    return "; ".join(messages)


class BulkImportService:
    def __init__(self, session: AsyncSession) -> None:
        self._classrooms = ClassroomService(session)
        self._subjects = SubjectService(session)
        self._teachers = TeacherProfileService(session)
        self._students = StudentProfileService(session)

    async def _create_row(self, entity: BulkImportEntity, row: dict[str, object]) -> None:
        if entity is BulkImportEntity.CLASSROOMS:
            await self._classrooms.create(ClassroomCreate.model_validate(row))
        elif entity is BulkImportEntity.SUBJECTS:
            await self._subjects.create(SubjectCreate.model_validate(row))
        elif entity is BulkImportEntity.TEACHER_PROFILES:
            await self._teachers.create(TeacherProfileCreate.model_validate(row))
        else:
            await self._students.create(StudentProfileCreate.model_validate(row))

    async def import_file(
        self,
        *,
        entity: BulkImportEntity,
        filename: str,
        content: bytes,
    ) -> BulkImportResult:
        rows = parse_import_file(filename=filename, content=content)
        expected_columns = _EXPECTED_COLUMNS[entity]
        errors: list[BulkImportRowError] = []
        imported_count = 0

        for row_number, row in rows:
            unexpected = sorted(set(row) - expected_columns)
            if unexpected:
                errors.append(
                    BulkImportRowError(
                        row_number=row_number,
                        code="BULK_IMPORT_UNKNOWN_COLUMNS",
                        message=f"Unknown column(s): {', '.join(unexpected)}.",
                    )
                )
                continue
            try:
                await self._create_row(entity, row)
            except ValidationError as exc:
                errors.append(
                    BulkImportRowError(
                        row_number=row_number,
                        code="BULK_IMPORT_ROW_VALIDATION_ERROR",
                        message=_validation_message(exc),
                    )
                )
            except AppError as exc:
                errors.append(
                    BulkImportRowError(
                        row_number=row_number,
                        code=exc.code,
                        message=exc.message,
                    )
                )
            else:
                imported_count += 1

        if not rows:
            raise BulkImportFileError("The import file contains no data rows.")
        return BulkImportResult(
            entity=entity,
            success=not errors,
            total_rows=len(rows),
            imported_count=imported_count,
            failed_count=len(errors),
            errors=errors,
        )
