"""Structural regressions for the Stage 4 AttendanceService boundary."""

from __future__ import annotations

import ast
from pathlib import Path


def _face_recognition_python_files() -> list[Path]:
    module_dir = Path(__file__).parents[1] / "modules" / "face_recognition"
    return sorted(module_dir.glob("*.py"))


def test_face_recognition_never_imports_attendance_write_repository_or_record_model() -> None:
    forbidden_imports: list[tuple[Path, str]] = []
    for path in _face_recognition_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            for imported in node.names:
                if imported.name in {"AttendanceRepository", "AttendanceRecord"}:
                    forbidden_imports.append((path, imported.name))
    assert forbidden_imports == []


def test_only_stage4_orchestrator_imports_attendance_service() -> None:
    importers: list[str] = []
    for path in _face_recognition_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module == "app.modules.attendance.service" and any(
                imported.name == "AttendanceService" for imported in node.names
            ):
                importers.append(path.name)
    assert importers == ["recognition_attendance_service.py"]


def test_stage4_orchestrator_uses_attendance_service_for_both_confirmation_paths() -> None:
    path = next(
        path
        for path in _face_recognition_python_files()
        if path.name == "recognition_attendance_service.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "bulk_save"
    ]
    assert len(calls) == 2
