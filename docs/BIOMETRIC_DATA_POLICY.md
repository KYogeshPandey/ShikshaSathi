# Biometric Data Policy

This policy describes how ShikshaSathi handles face images, aligned face
crops, embeddings, recognition decisions, and related identifiers.

## Scope and legal notice

This is an application-design policy, not legal advice. Laws governing student
biometrics, consent, parental authorization, retention, deletion, and cross-
border processing vary by jurisdiction. Before using real biometric data, the
deploying organization must complete its own legal, privacy, safeguarding, and
security review.

The public portfolio repository is intended to use synthetic test data. It
contains no real student face images, generated embeddings, recognition
captures, or model weights.

## Purpose and consent

Biometric data may be processed only for the explicit purpose of assisting an
authorized teacher with attendance. It must not be reused for surveillance,
discipline, profiling, general analytics, model training, marketing, or an
unrelated identity search.

ShikshaSathi does not implement a complete legal consent-management system.
Before enrollment, the deploying school is responsible for obtaining and
recording all required student/parental consent and institutional approval,
providing an appropriate alternative attendance method, and defining how
consent withdrawal triggers deletion.

## Data categories

| Data | Handling |
|---|---|
| Enrollment image | Stored in private application storage while the enrollment is active and operationally required |
| Aligned face crop | Transient in-memory pipeline value; not persisted |
| Enrollment embedding | Stored in PostgreSQL for active candidate matching; never exposed by the application API |
| Classroom attendance image | Processed only for the bounded request; not retained |
| Per-request embedding | Transient in memory; not retained |
| Recognition review | Stores bounded scope/candidate/decision/confirmation identifiers, never image bytes or embeddings |

All artifacts are linked by server-side UUIDs to a `StudentProfile`, never by
a filename, display name, or roll number as the authoritative identity key.

## Access control

- **Enrollment, replacement, and deletion:** administrator only.
- **Enrollment metadata:** administrators and the owning student only. Another
  student's record is concealed as a normal not-found response.
- **Raw images and embeddings:** never returned by normal application APIs to
  any role.
- **Recognition attendance:** administrator or a teacher with the exact active
  classroom/subject assignment. Teacher access does not grant enrollment or
  biometric-inspection rights.
- **Student access:** students cannot enroll themselves, select another
  student, or inspect another student's biometric state.

Authorization and the active roster are derived from the authenticated user
and PostgreSQL relationships. Client-provided candidate lists, identities, or
match results are never trusted.

## Private storage

Enrollment files live below `BIOMETRIC_STORAGE_ROOT`, outside any public/static
web directory. Startup validation rejects obviously public storage paths, but
the deployer must still verify actual filesystem permissions and topology.

The storage adapter uses server-generated opaque keys and separate zones:

```text
staging/       validated before activation
active/        current enrollment sample
quarantine/    deletion/replacement recovery state
bulk_staging/  bounded ZIP ingestion workspace
```

Uploaded filenames never become filesystem paths. Promotion and quarantine
use same-filesystem atomic renames where possible. Database transactions
cannot make filesystem operations atomic, so transitions use explicit pending
states, compensating cleanup, and a read-only reconciliation report to expose
database/filesystem drift.

## Upload and archive restrictions

Single enrollment images are restricted by content type, encoded size,
dimensions, pixel count, decodability, and supported format. A decoded image
must satisfy the configured bounds before it is accepted.

Bulk enrollment accepts a bounded ZIP with a root `manifest.csv`. Before any
member is used, the archive is checked for traversal, absolute/drive/UNC
paths, symlinks or special entries, encryption, nested archives, duplicate
normalized paths, unreferenced files, member count, compressed/uncompressed
size, and suspicious compression ratios. Application code does not use
`ZipFile.extract()` or `extractall()` on untrusted archives.

Uploaded names do not determine final storage keys. Duplicate content for the
same active enrollment is rejected; identical content across different
students is not treated as proof of identity.

## Enrollment lifecycle, retention, and deletion

Enrollment and sample records use explicit pending, active, replacement,
quarantine, and deleted states. Only active samples with successfully
processed active embeddings are eligible for matching.

Biometric data must be retained only while the documented attendance purpose,
valid consent, and active student relationship remain. A production deployment
must define a concrete bounded retention period and deletion service level.
Indefinite retention is not acceptable.

On withdrawal, deactivation, replacement, or deletion:

1. make the artifact ineligible for matching;
2. transition it through the documented deletion/quarantine lifecycle;
3. remove associated embeddings and files according to the deployment's
   retention schedule;
4. verify completion through reconciliation and audit records.

The application provides lifecycle and reconciliation primitives but no
always-running background worker. Operators must schedule and monitor purge
and reconciliation procedures. General code/database exports must not
incidentally copy the private biometric volume. If biometric backups are
required, they need a separate encrypted, access-controlled, retention-bound
process.

## Recognition and attendance boundary

Recognition is decision support, not autonomous attendance marking.

1. The teacher's exact classroom/subject scope is authorized.
2. The active classroom roster is derived server-side.
3. The bounded classroom image is decoded and processed in memory.
4. Detected faces are aligned, embedded, and matched only against that roster.
5. The system returns non-writing proposals for teacher review.
6. Only statuses explicitly selected and confirmed by the authorized teacher
   are written through the existing attendance service.

Every outcome—including `FOUND`—is a proposal. Unknown, ambiguous,
low-confidence, duplicate, missed, or unmarked faces never imply absence and
never write attendance automatically. Confirmation rechecks authorization and
current roster membership before persistence.

The recognition/provider layer does not write attendance records directly.
Attendance transactions, uniqueness rules, attribution, and audit behavior
remain owned by `AttendanceService`.

## API, logging, audit, and export restrictions

Application responses, logs, audit metadata, reports, and exports must not
contain:

- enrollment/classroom image bytes or public image URLs;
- aligned crops or embedding vectors;
- filesystem paths or model paths;
- raw provider exceptions or stack traces;
- credentials, tokens, hashes, or secret configuration.

Safe metadata may include bounded UUIDs, action/outcome codes, timestamps,
scope identifiers, candidate counts, and confirmation/attendance identifiers.
Enrollment, replacement, deletion, recognition decisions, confirmations, and
blocked authorization attempts are auditable without storing biometric
payloads in the audit log.

Provider health responses expose only coarse bounded status. They must not
reveal server layout, model file locations, vendor response bodies, or detailed
runtime fingerprints.

## Models, providers, and accuracy

The optional local provider uses:

- OpenCV YuNet for face detection;
- landmark-based alignment;
- dlib's 128-dimensional ResNet face embedding adapter;
- L2-normalized cosine similarity and ambiguity handling.

Model files are independently obtained deployment artifacts. They are not
downloaded automatically, committed to Git, included in source archives, or
embedded in production images. Deployers must verify provenance, licensing,
integrity hashes, update procedures, and storage permissions for the exact
files they use.

The default similarity threshold and ambiguity margin are provisional
structural defaults, not calibration against ShikshaSathi classrooms. Published
third-party benchmark figures are not evidence of accuracy, fairness, or
suitability for a particular school. Production evaluation requires
representative, consented data and documented false-accept/false-reject results
across relevant lighting, camera, demographic, occlusion, and classroom
conditions.

## Production limitations and required safeguards

`FACE_RECOGNITION_PROVIDER=none` is the safe default and may remain active in
the hosted portfolio deployment. In that configuration, hosted face inference
is unavailable even though the enrollment/review architecture exists.

Before any real biometric deployment, operators must at minimum:

1. complete legal, privacy, consent, and safeguarding review;
2. define retention, deletion, backup, incident-response, and access-review
   procedures;
3. supply vetted model artifacts and verify integrity;
4. calibrate and monitor accuracy/fairness on representative consented data;
5. add and validate appropriate liveness/anti-spoofing controls;
6. secure and back up PostgreSQL and biometric storage separately;
7. monitor reconciliation, purge, audit, and provider-health outcomes;
8. maintain a fully functional manual attendance alternative.

Until those controls exist, face recognition should remain disabled and no
claim should be made that the hosted portfolio deployment supports operational
biometric attendance.
