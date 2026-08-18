"""Pure unit tests for app/modules/bulk_imports/parser.py normalization.

None of these need a database or HTTP client, so this file always runs
(unlike the database-backed suites — see app/tests/conftest.py).

Some cases (NaN/infinity) cannot be produced through a real XLSX
round-trip: openpyxl's own writer silently drops both down to an empty
cell (``None``) on write, so a workbook built and read with openpyxl can
never actually hand the parser a ``float('nan')``/``float('inf')`` value
in the first place. That was verified directly against the installed
openpyxl before writing this file. The defensive rejection in
``_normalized_scalar`` still guards against a workbook authored by some
other tool that *can* round-trip those values, so it is tested by
calling the normalization helper directly rather than via a workbook
that cannot express the input.
"""

from __future__ import annotations

import pytest

from app.modules.bulk_imports.errors import BulkImportFileError
from app.modules.bulk_imports.parser import _normalized_row, _normalized_scalar


def test_int_cells_normalize_to_plain_decimal_strings() -> None:
    assert _normalized_scalar("code", 12) == "12"
    assert _normalized_scalar("code", 0) == "0"
    assert _normalized_scalar("code", -3) == "-3"


def test_whole_number_float_cells_normalize_without_trailing_zero() -> None:
    # Excel's default "General" format for a typed whole number reads back
    # from openpyxl as this exact case (and, separately, often as a bare
    # ``int`` — both are covered since both branches return "12").
    assert _normalized_scalar("code", 12.0) == "12"
    assert _normalized_scalar("roll_number", 5.0) == "5"


def test_decimal_float_cells_normalize_without_unnecessary_trailing_zeroes() -> None:
    assert _normalized_scalar("value", 12.5) == "12.5"
    assert _normalized_scalar("value", 0.1 + 0.2) == "0.3"


def test_bool_cells_are_preserved_not_stringified() -> None:
    # A real bool must stay a bool for Pydantic's `is_elective: bool` field
    # instead of becoming the identifier-shaped string "True"/"False".
    assert _normalized_scalar("is_elective", True) is True
    assert _normalized_scalar("is_elective", False) is False


def test_nan_cell_is_rejected() -> None:
    with pytest.raises(BulkImportFileError):
        _normalized_scalar("code", float("nan"))


def test_infinite_cell_is_rejected() -> None:
    with pytest.raises(BulkImportFileError):
        _normalized_scalar("code", float("inf"))
    with pytest.raises(BulkImportFileError):
        _normalized_scalar("code", float("-inf"))


def test_other_object_types_pass_through_unchanged() -> None:
    # The fix is deliberately narrow: anything that isn't str/bool/int/float
    # (e.g. a cell holding a datetime) is left alone rather than being
    # broadly coerced, and will surface as a normal Pydantic validation
    # error further downstream if the target field can't accept it.
    marker = object()
    assert _normalized_scalar("misc", marker) is marker


def test_normalized_row_strips_strings_and_skips_blank_and_none_values() -> None:
    row = _normalized_row(
        ["name", "code", "grade_level", "section"],
        ["  Grade 7  ", "g7-a", "", None],
    )
    assert row == {"name": "Grade 7", "code": "g7-a"}


def test_normalized_row_applies_scalar_normalization_per_header() -> None:
    row = _normalized_row(
        ["name", "code", "grade_level", "section"],
        ["Grade 12", 12.0, 12, "A"],
    )
    assert row == {"name": "Grade 12", "code": "12", "grade_level": "12", "section": "A"}
