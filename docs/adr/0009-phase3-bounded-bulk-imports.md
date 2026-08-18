# ADR 0009: Bounded academic CSV/XLSX imports

## Status

Accepted.

## Context

Phase 3 requires CSV/Excel import with schema validation, row limits, and
per-row errors. The legacy implementation decoded an entire CSV or loaded an
Excel workbook through pandas without file or row limits, broadly caught
exceptions, and returned raw row values. Phase 3 final integration must close
that audit finding without adding Phase 4 behavior.

## Decisions

1. One admin-only endpoint, `POST /api/v1/imports/{entity}`, supports
   `classrooms`, `subjects`, `teacher-profiles`, and `student-profiles`.
2. Imports accept UTF-8 CSV and XLSX only. CSV uses the standard library;
   XLSX uses openpyxl in read-only/data-only mode.
3. Files are limited to 2 MiB and 500 non-blank data rows. Unsupported,
   empty, malformed, oversized, or over-limit files raise stable errors
   through the normal request-ID envelope.
4. Every row is validated through the same strict Pydantic create schema and
   existing service used by the corresponding JSON endpoint. Successful
   rows commit independently; expected validation/domain failures are
   reported with row number, stable code, and safe message.
5. Error responses never echo the submitted row. This avoids reflecting
   identifiers or future sensitive columns into logs or clients.
6. Teacher/student profile imports link only to existing role-correct active
   users. Account credential provisioning is not invented inside a file
   import; it remains an identity-management concern.

## Consequences

- A partially valid file returns HTTP 200 with `success=false`, accurate
  imported/failed counts, and a per-row error list. File-level failures use
  the standard non-2xx error envelope.
- Duplicate codes, profile conflicts, invalid references, inactive users,
  and inactive classroom membership reuse existing stable domain errors.
- The endpoint remains synchronous and intentionally capped; background jobs
  and very large imports are outside Phase 3.
