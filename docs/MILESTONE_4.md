# Milestone 4 Operations Guide

## Demo dataset

From `backend_v2`:

```powershell
python -m scripts.seed_demo_data --dry-run
python -m scripts.seed_demo_data
python -m scripts.seed_demo_data --reset-demo
```

The manifest contains 15 synthetic users (1 admin, 2 teachers, 12 students),
2 classrooms, 3 subjects, 6 assignments, 10 timetable entries,
3 announcements, and deterministic weekday attendance within the previous
30 days. Stable UUIDv5 identifiers make the operation idempotent. The reset
removes only deterministic demo history/relationships before recreating them;
tests prove an unrelated user and announcement survive.

Passwords are read from an uncommitted `DEMO_SEED_PASSWORD` value or a
non-echoing prompt. Default emails use `.example`. Override only the documented
selected account email settings when a controlled inbox is needed.

No seed runs at startup. Production writes are rejected unless
`DEMO_SEED_ALLOW_PRODUCTION=true`; that opt-in is appropriate only for a
deliberately selected demo environment, never a real school database.

## Image-assisted attendance

Use the existing enrollment UI/API to enroll synthetic or explicitly
consented demo participants. Keep source images outside Git. Automated tests
use generated image bytes and synthetic embeddings, not human biometric data.

The teacher chooses an authorized classroom, subject, date, and image. The
backend validates/decodes the bounded upload, detects all faces up to the
configured limit, matches only against the server-derived active roster, and
returns proposals. It retains neither the classroom image nor per-request
embeddings. The teacher reviews each roster student as unmarked, present, or
absent. Only explicitly selected records are saved on confirmation through the
existing attendance service. Missing, unknown, ambiguous, and duplicate faces
never imply absence.

The production free-tier profile remains disabled with
`FACE_RECOGNITION_PROVIDER=none`. Local recognition requires independently
obtained/integrity-checked YuNet and dlib model files and sufficient native
resources. No hosted-recognition capability is claimed without that setup.

## Email OTP

OTP is opt-in. Disabled mode preserves direct email/password login. Enabled
mode performs:

```text
registered active user's email + password
  -> hashed, expiring challenge + email
  -> OTP verification
  -> existing JWT access token + rotating refresh session
```

Configure either:

- Local only: `APP_ENV=development`, `LOGIN_OTP_ENABLED=true`,
  `OTP_EMAIL_PROVIDER=development_log`.
- Production: `LOGIN_OTP_ENABLED=true`, `OTP_EMAIL_PROVIDER=smtp`, plus
  `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM_EMAIL`, and—when required by the
  provider—both `SMTP_USERNAME` and `SMTP_PASSWORD`. Configure
  exactly one appropriate transport mode (`SMTP_STARTTLS` or
  `SMTP_USE_SSL`) and `SMTP_TIMEOUT_SECONDS` for that provider. Production
  rejects plaintext SMTP.

Never put real values in `.env.example` or source. The development-log adapter
is rejected at production startup. No provider account is created
automatically. Apply Alembic migrations before enabling OTP.

The server enforces a 5–10 minute configured expiry, cryptographic six-digit
generation, keyed hash-only storage, one-time consumption, attempt maximum,
resend cooldown/replacement, and independent per-client endpoint limits. OTPs
are not returned by the production API. Any syntactically valid registered
email works regardless of domain; this does not add self-registration.
