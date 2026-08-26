import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, type FormEvent, type ReactNode } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { academicsApi } from "../api/academics";
import { apiErrorMessage } from "../api/errorMessage";
import { importsApi } from "../api/imports";
import { queryKeys } from "../api/queryKeys";
import { SlowRequestNotice } from "../components/SlowRequestNotice";
import type {
  BulkImportEntity,
  StudentOnboardingStudentResult,
} from "../types/domain";

const MAX_IMPORT_BYTES = 2 * 1024 * 1024;
const importSchema = z.object({
  entity: z.enum(["classrooms", "subjects", "teacher-profiles", "student-profiles"]),
  classroom_id: z.string(),
  update_existing: z.boolean(),
});

interface ImportFormValues {
  entity: BulkImportEntity;
  classroom_id: string;
  update_existing: boolean;
}

function statusPill(kind: "success" | "failure" | "neutral", label: string): ReactNode {
  const symbol = kind === "success" ? "✓" : kind === "failure" ? "✕" : "—";
  const modifier = kind === "success" ? "present" : kind === "failure" ? "absent" : "neutral";
  return (
    <span className={`status-pill status-pill--${modifier}`}>
      <span aria-hidden="true">{symbol}</span> {label}
    </span>
  );
}

function profileStatus(student: StudentOnboardingStudentResult): ReactNode {
  if (student.profile_status === "created") return statusPill("success", "Created");
  if (student.profile_status === "updated") return statusPill("success", "Updated");
  if (student.profile_status === "reactivated") return statusPill("success", "Reactivated");
  if (student.profile_status === "existing") return statusPill("neutral", "Already exists");
  return statusPill("failure", "Failed");
}

function photoStatus(student: StudentOnboardingStudentResult): ReactNode {
  if (student.photo_status === "matched") {
    return statusPill("success", student.photo_filename ?? "Matched");
  }
  if (student.photo_status === "not_provided") return statusPill("neutral", "Not provided");
  if (student.photo_status === "missing") return statusPill("failure", "Missing");
  if (student.photo_status === "duplicate") return statusPill("failure", "Duplicate");
  return statusPill("failure", "Invalid");
}

function biometricStatus(student: StudentOnboardingStudentResult): ReactNode {
  if (student.biometric_status === "enrolled") return statusPill("success", "Face enrolled");
  if (student.biometric_status === "already_enrolled") {
    return statusPill("neutral", "Already enrolled");
  }
  if (student.biometric_status === "failed") return statusPill("failure", "Failed");
  return statusPill("neutral", "Not processed");
}

export function AdminImportsPage() {
  const form = useForm<ImportFormValues>({
    defaultValues: { entity: "classrooms", classroom_id: "", update_existing: false },
  });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const photosInputRef = useRef<HTMLInputElement>(null);
  const selectedEntity = useWatch({ control: form.control, name: "entity" });
  const isStudentOnboarding = selectedEntity === "student-profiles";
  const classrooms = useQuery({
    queryKey: queryKeys.classrooms,
    queryFn: () => academicsApi.listClassrooms(),
    enabled: isStudentOnboarding,
  });
  const importMutation = useMutation({
    mutationFn: ({ entity, file }: { entity: BulkImportEntity; file: File }) =>
      importsApi.upload(entity, file),
  });
  const onboardingMutation = useMutation({
    mutationFn: ({
      classroomId,
      studentsFile,
      photosZip,
      updateExisting,
    }: {
      classroomId: string;
      studentsFile: File;
      photosZip?: File;
      updateExisting: boolean;
    }) => importsApi.onboard(classroomId, studentsFile, photosZip, updateExisting),
  });
  const isPending = importMutation.isPending || onboardingMutation.isPending;

  const submitValues = (values: ImportFormValues) => {
    importMutation.reset();
    onboardingMutation.reset();
    const parsed = importSchema.safeParse(values);
    if (!parsed.success) return;
    if (parsed.data.entity === "student-profiles" && !parsed.data.classroom_id) {
      form.setError("classroom_id", { message: "Choose a classroom for this batch." });
      return;
    }
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      form.setError("root", { message: "Choose a CSV or XLSX file." });
      return;
    }
    const extension = file.name.split(".").pop()?.toLowerCase();
    if (extension !== "csv" && extension !== "xlsx") {
      form.setError("root", { message: "Only CSV and XLSX files are accepted." });
      return;
    }
    if (file.size > MAX_IMPORT_BYTES) {
      form.setError("root", { message: "The import file must be 2 MiB or smaller." });
      return;
    }

    const photosZip = photosInputRef.current?.files?.[0];
    if (isStudentOnboarding && photosZip && !photosZip.name.toLowerCase().endsWith(".zip")) {
      form.setError("root", { message: "Student photos must be provided as a ZIP file." });
      return;
    }

    form.clearErrors("root");
    if (parsed.data.entity === "student-profiles") {
      onboardingMutation.mutate({
        classroomId: parsed.data.classroom_id,
        studentsFile: file,
        photosZip,
        updateExisting: parsed.data.update_existing,
      });
    } else {
      importMutation.mutate({ entity: parsed.data.entity, file });
    }
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    void form.handleSubmit(submitValues)(event);
  };

  const requestError = importMutation.error ?? onboardingMutation.error;

  return (
    <section className="page-stack">
      <div className="page-heading">
        <p className="eyebrow">Administration</p>
        <h1>Bulk imports</h1>
        <p>
          Upload at most 500 classroom, subject, teacher-profile, or student-profile rows per
          CSV/XLSX file.
        </p>
      </div>
      <form className="form-card" onSubmit={submit} noValidate>
        {isStudentOnboarding ? (
          <>
            <div className="workflow-heading">
              <p className="eyebrow">Guided import</p>
              <h2>Student onboarding</h2>
            </div>
            <ol className="onboarding-steps" aria-label="Student onboarding steps">
              <li className="onboarding-step">
                <span className="onboarding-step__number">1</span>
                <div><strong>Select classroom</strong><span>Choose the destination class for this roster.</span></div>
              </li>
              <li className="onboarding-step">
                <span className="onboarding-step__number">2</span>
                <div><strong>Upload spreadsheet</strong><span>Add the reviewed student CSV or XLSX file.</span></div>
              </li>
              <li className="onboarding-step">
                <span className="onboarding-step__number">3</span>
                <div><strong>Add photos (optional)</strong><span>Include a roll-number-matched ZIP for enrollment.</span></div>
              </li>
            </ol>
          </>
        ) : null}
        <div className="form-grid">
          <label className="field">
            <span>Record type</span>
            <select {...form.register("entity")}>
              <option value="classrooms">Classrooms</option>
              <option value="subjects">Subjects</option>
              <option value="teacher-profiles">Teacher profiles</option>
              <option value="student-profiles">Student profiles</option>
            </select>
          </label>
          {isStudentOnboarding ? (
            <label className="field">
              <span>Classroom</span>
              <select
                aria-label="Classroom"
                aria-describedby={
                  form.formState.errors.classroom_id
                    ? "onboarding-classroom-help onboarding-classroom-error"
                    : "onboarding-classroom-help"
                }
                aria-invalid={Boolean(form.formState.errors.classroom_id)}
                disabled={isPending || classrooms.isPending}
                {...form.register("classroom_id")}
              >
                <option value="">Choose a classroom</option>
                {classrooms.data?.items.map((classroom) => (
                  <option key={classroom.id} value={classroom.id}>
                    {classroom.name}
                  </option>
                ))}
              </select>
              <small id="onboarding-classroom-help">
                All students in this upload will be assigned to the selected classroom.
              </small>
              {form.formState.errors.classroom_id?.message ? (
                <small className="field-error" id="onboarding-classroom-error">
                  {form.formState.errors.classroom_id.message}
                </small>
              ) : null}
            </label>
          ) : null}
          {isStudentOnboarding ? (
            <label className="checkbox-option onboarding-update-option">
              <input
                disabled={isPending}
                type="checkbox"
                {...form.register("update_existing")}
              />
              <span>
                <strong>Update existing student profiles</strong>
                <small>
                  When enabled, existing students can be moved to the selected classroom and
                  their roll number can be updated. Existing biometric enrollments are never
                  overwritten automatically.
                </small>
                <small>
                  Inactive student profiles will be reactivated when updated through this
                  onboarding batch.
                </small>
              </span>
            </label>
          ) : null}
          <label className="field">
            <span>{isStudentOnboarding ? "Student CSV or XLSX" : "CSV or XLSX file"}</span>
            <input
              ref={fileInputRef}
              accept=".csv,.xlsx"
              aria-label={isStudentOnboarding ? "Student CSV or XLSX" : "CSV or XLSX file"}
              type="file"
            />
            {isStudentOnboarding ? (
              <small>Any classroom value inside the file is ignored for this onboarding batch.</small>
            ) : null}
          </label>
          {isStudentOnboarding ? (
            <label className="field">
              <span>Student photos ZIP (optional)</span>
              <input
                ref={photosInputRef}
                accept=".zip,application/zip"
                aria-label="Student photos ZIP (optional)"
                type="file"
              />
              <small>Name each photo with the student's roll number, such as 101.jpg.</small>
            </label>
          ) : null}
        </div>
        {isStudentOnboarding && classrooms.data?.items.length === 0 ? (
          <p className="empty-state">No classrooms available. Create a classroom first.</p>
        ) : null}
        {classrooms.error ? (
          <p className="error-message" role="alert">{apiErrorMessage(classrooms.error)}</p>
        ) : null}
        <button
          className="button button--primary"
          disabled={
            isPending ||
            (isStudentOnboarding && (classrooms.isPending || classrooms.data?.items.length === 0))
          }
          type="submit"
        >
          {isPending
            ? isStudentOnboarding
              ? "Validating and importing..."
              : "Importing..."
            : isStudentOnboarding
              ? "Validate & Import"
              : "Run import"}
        </button>
        {form.formState.errors.root?.message ? (
          <p className="error-message" role="alert">
            {form.formState.errors.root.message}
          </p>
        ) : null}
        {requestError ? (
          <p className="error-message" role="alert">
            {apiErrorMessage(requestError)}
          </p>
        ) : null}
        {isPending ? <SlowRequestNotice /> : null}
      </form>

      {importMutation.data ? (
        <div className="table-card" aria-live="polite">
          <h2>Import result</h2>
          <p>
            {importMutation.data.imported_count} imported; {importMutation.data.failed_count} failed
            out of {importMutation.data.total_rows} rows.
          </p>
          {importMutation.data.errors.length ? (
            <div className="table-scroll" role="region" aria-label="Import row errors" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Code</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {importMutation.data.errors.map((error) => (
                    <tr key={`${error.row_number}-${error.code}`}>
                      <td>{error.row_number}</td>
                      <td>{error.code}</td>
                      <td>{error.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="success-message">The import completed without row errors.</p>
          )}
        </div>
      ) : null}

      {onboardingMutation.data ? (
        <div className="table-card" aria-live="polite">
          <div className="table-card__header">
            <h2>Student onboarding result</h2>
            <span>
              {onboardingMutation.data.profile_success_count} profiles; {onboardingMutation.data.face_success_count}
              {" "}faces enrolled
            </span>
          </div>
          <div className="onboarding-summary" aria-label="Student onboarding summary">
            <div><span>Profiles ready</span><strong>{onboardingMutation.data.profile_success_count}</strong></div>
            <div><span>Faces enrolled</span><strong>{onboardingMutation.data.face_success_count}</strong></div>
            <div>
              <span>Need attention</span>
              <strong>
                {onboardingMutation.data.students.filter((student) => student.issues.length > 0).length +
                  onboardingMutation.data.unmatched_files.length}
              </strong>
            </div>
          </div>
          <div className="table-scroll" role="region" aria-label="Student onboarding results" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Roll</th>
                  <th>Classroom</th>
                  <th>Profile</th>
                  <th>Photo</th>
                  <th>Face enrollment</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {onboardingMutation.data.students.map((student) => (
                  <tr key={student.row_number}>
                    <td>{student.full_name ?? `Spreadsheet row ${student.row_number}`}</td>
                    <td>{student.roll_number ?? "—"}</td>
                    <td>
                      {student.profile_status === "existing"
                        ? "Unchanged"
                        : onboardingMutation.data.classroom_name}
                    </td>
                    <td>{profileStatus(student)}</td>
                    <td>{photoStatus(student)}</td>
                    <td>{biometricStatus(student)}</td>
                    <td>
                      {student.issues.length
                        ? student.issues.map((issue) => issue.message).join(" ")
                        : "Completed successfully."}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {onboardingMutation.data.unmatched_files.length ? (
            <div className="onboarding-unmatched">
              <h3>Unmatched ZIP files</h3>
              <ul>
                {onboardingMutation.data.unmatched_files.map((file) => (
                  <li key={`${file.filename}-${file.code}`}>
                    <strong>{file.filename}</strong>: {file.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
