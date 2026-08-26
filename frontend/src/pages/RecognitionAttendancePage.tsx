import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { academicsApi } from "../api/academics";
import { attendanceApi } from "../api/attendance";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { recognitionApi } from "../api/recognition";
import { SlowRequestNotice } from "../components/SlowRequestNotice";
import type { AttendanceStatus, RecognitionAttendanceReview } from "../types/domain";

interface RecognitionScopeValues {
  classroom_id: string;
  subject_id: string;
  attendance_date: string;
}

type ReviewStatus = AttendanceStatus | "";

const recognitionSchema = z.object({
  classroom_id: z.string().uuid("Choose a classroom."),
  subject_id: z.string().uuid("Choose a subject."),
  attendance_date: z.string().date("Choose a valid date."),
});

function localDate(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 10);
}

function studentInitials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  return `${parts[0]?.[0] ?? "S"}${parts.length > 1 ? parts.at(-1)?.[0] ?? "" : ""}`.toUpperCase();
}

export function RecognitionAttendancePage() {
  const client = useQueryClient();
  const form = useForm<RecognitionScopeValues>({
    defaultValues: { classroom_id: "", subject_id: "", attendance_date: localDate() },
  });
  const [file, setFile] = useState<File | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isCameraOn, setIsCameraOn] = useState(false);
  const [review, setReview] = useState<RecognitionAttendanceReview | null>(null);
  const [statuses, setStatuses] = useState<Record<string, ReviewStatus>>({});
  const [confirmed, setConfirmed] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const classrooms = useQuery({
    queryKey: queryKeys.classrooms,
    queryFn: () => academicsApi.listClassrooms(),
  });
  const subjects = useQuery({
    queryKey: queryKeys.subjects,
    queryFn: () => academicsApi.listSubjects(),
  });
  const optionsLoading = classrooms.isPending || subjects.isPending;

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setIsCameraOn(false);
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  useEffect(
    () => () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
    },
    [],
  );

  const startCamera = async () => {
    setCameraError(null);
    stopCamera();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      setIsCameraOn(true);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
    } catch {
      setCameraError("Camera access was unavailable. Choose an image file instead.");
    }
  };

  const capture = async () => {
    const video = videoRef.current;
    if (!video || !streamRef.current) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const context = canvas.getContext("2d");
    if (!context) {
      setCameraError("The camera image could not be captured.");
      return;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.9),
    );
    if (!blob) {
      setCameraError("The camera image could not be captured.");
      return;
    }
    setFile(new File([blob], `attendance-${Date.now()}.jpg`, { type: "image/jpeg" }));
    stopCamera();
  };

  const createReview = useMutation({
    mutationFn: ({ values, image }: { values: RecognitionScopeValues; image: File }) =>
      recognitionApi.createReview({
        classroomId: values.classroom_id,
        subjectId: values.subject_id,
        attendanceDate: values.attendance_date,
        file: image,
      }),
    onSuccess: (result) => {
      setReview(result);
      setStatuses({});
      setConfirmed(false);
    },
  });

  const roster = useQuery({
    queryKey: review
      ? queryKeys.attendanceRoster(review.classroom_id, review.subject_id)
      : [...queryKeys.attendance, "roster", "recognition-idle"],
    queryFn: () =>
      attendanceApi.getRoster({
        classroomId: review!.classroom_id,
        subjectId: review!.subject_id,
      }),
    enabled: Boolean(review),
  });

  const proposedPresent = new Set(
    review?.proposals
      .filter(
        (proposal) =>
          proposal.decision === "found" &&
          !proposal.is_duplicate &&
          proposal.matched_student_profile_id,
      )
      .map((proposal) => proposal.matched_student_profile_id as string) ?? [],
  );
  const statusFor = (studentId: string): ReviewStatus =>
    statuses[studentId] ?? (proposedPresent.has(studentId) ? "present" : "");
  const selectedRecords =
    roster.data
      ?.map((student) => ({
        student_profile_id: student.student_profile_id,
        status: statusFor(student.student_profile_id),
      }))
      .filter(
        (record): record is { student_profile_id: string; status: AttendanceStatus } =>
          record.status !== "",
      ) ?? [];

  const confirm = useMutation({
    mutationFn: () => recognitionApi.confirmReview(review!.review_id, selectedRecords),
    onSuccess: async () => {
      setConfirmed(true);
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.attendance }),
        client.invalidateQueries({ queryKey: ["analytics"] }),
        client.invalidateQueries({ queryKey: queryKeys.reports }),
      ]);
    },
  });

  const submit = form.handleSubmit((values) => {
    createReview.reset();
    setReview(null);
    const parsed = recognitionSchema.safeParse(values);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        form.setError(issue.path[0] as keyof RecognitionScopeValues, {
          message: issue.message,
        });
      }
      return;
    }
    if (!file) {
      form.setError("root", { message: "Capture or choose an image before submitting." });
      return;
    }
    form.clearErrors("root");
    createReview.mutate({ values: parsed.data, image: file });
  });

  const unresolvedFaces = review?.proposals.filter(
    (proposal) => proposal.decision !== "found",
  ).length;
  const duplicateFaces = review?.proposals.filter((proposal) => proposal.is_duplicate).length;

  return (
    <section className="page-stack">
      <div className="page-heading">
        <p className="eyebrow">Teacher attendance</p>
        <h1>Recognition attendance</h1>
        <p>
          Capture or upload an image, review every suggestion, and explicitly confirm before
          attendance is saved.
        </p>
      </div>
      <form className="form-card recognition-form" onSubmit={submit} noValidate>
        <div className="form-grid">
          <label className="field">
            <span>Classroom</span>
            <select disabled={optionsLoading} {...form.register("classroom_id")}>
              <option value="">Select classroom</option>
              {classrooms.data?.items.map((item) => (
                <option key={item.id} value={item.id}>{item.name} ({item.code})</option>
              ))}
            </select>
            {form.formState.errors.classroom_id?.message ? (
              <small className="field-error">{form.formState.errors.classroom_id.message}</small>
            ) : null}
          </label>
          <label className="field">
            <span>Subject</span>
            <select disabled={optionsLoading} {...form.register("subject_id")}>
              <option value="">Select subject</option>
              {subjects.data?.items.map((item) => (
                <option key={item.id} value={item.id}>{item.name} ({item.code})</option>
              ))}
            </select>
            {form.formState.errors.subject_id?.message ? (
              <small className="field-error">{form.formState.errors.subject_id.message}</small>
            ) : null}
          </label>
          <label className="field">
            <span>Date</span>
            <input type="date" {...form.register("attendance_date")} />
            {form.formState.errors.attendance_date?.message ? (
              <small className="field-error">{form.formState.errors.attendance_date.message}</small>
            ) : null}
          </label>
          <label className="field">
            <span>Image file fallback</span>
            <input
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              type="file"
            />
          </label>
        </div>
        <div className="camera-panel">
          <div className="camera-panel__heading">
            <div><h2>Camera or classroom image</h2><p>Capture once or choose a clear image, then create a proposal for teacher review.</p></div>
          </div>
          <video aria-label="Camera preview" muted playsInline ref={videoRef} />
          <div className="button-row">
            <button className="button button--quiet" onClick={startCamera} type="button">Start camera</button>
            <button className="button button--quiet" disabled={!isCameraOn} onClick={capture} type="button">Capture image</button>
            <button className="button button--quiet" disabled={!isCameraOn} onClick={stopCamera} type="button">Stop camera</button>
          </div>
          {file ? <p className="capture-status">Ready: {file.name}</p> : null}
          {cameraError ? <p className="error-message" role="alert">{cameraError}</p> : null}
        </div>
        <button className="button button--primary" disabled={optionsLoading || createReview.isPending} type="submit">
          {optionsLoading ? "Loading options…" : createReview.isPending ? "Checking…" : "Create review"}
        </button>
        {optionsLoading || createReview.isPending ? <SlowRequestNotice /> : null}
        {form.formState.errors.root?.message ? <p className="error-message" role="alert">{form.formState.errors.root.message}</p> : null}
        {createReview.error ? <p className="error-message" role="alert">{apiErrorMessage(createReview.error)}</p> : null}
      </form>

      {review ? (
        <div className="table-card recognition-review" aria-live="polite">
          <div className="table-card__header">
            <h2>Review proposals</h2>
            <span>{review.face_count} {review.face_count === 1 ? "face" : "faces"} detected</span>
          </div>
          <div className="review-summary" aria-label="Recognition review summary">
            <div><span>Faces detected</span><strong>{review.face_count}</strong></div>
            <div><span>Proposed matches</span><strong>{proposedPresent.size}</strong></div>
            <div><span>Needs review</span><strong>{unresolvedFaces ?? 0}</strong></div>
          </div>
          {review.face_count === 0 ? <p className="empty-state">No faces were detected. Every student remains unmarked.</p> : null}
          {unresolvedFaces ? <p className="notice-message notice-message--warning" role="status">{unresolvedFaces} unknown or low-confidence {unresolvedFaces === 1 ? "face needs" : "faces need"} review.</p> : null}
          {duplicateFaces ? <p>{duplicateFaces} duplicate {duplicateFaces === 1 ? "detection was" : "detections were"} ignored in the proposed statuses.</p> : null}
          {roster.isPending ? <p>Loading class roster...</p> : null}
          {roster.error ? <p className="error-message" role="alert">{apiErrorMessage(roster.error)}</p> : null}
          {roster.data?.length ? (
            <div className="attendance-list">
              {roster.data.map((student) => (
                <div className="attendance-row" key={student.student_profile_id}>
                  <div className="attendance-student">
                    <span className="student-avatar" aria-hidden="true">{studentInitials(student.full_name)}</span>
                    <div>
                      <strong>{student.full_name}</strong>
                      <small>Roll {student.roll_number ?? "not assigned"}</small>
                    </div>
                  </div>
                  <div className="segmented" role="group" aria-label={`Attendance for ${student.full_name}, roll ${student.roll_number ?? "not assigned"}`}>
                    {(["", "present", "absent"] as const).map((status) => (
                      <button
                        aria-pressed={statusFor(student.student_profile_id) === status}
                        className={statusFor(student.student_profile_id) === status ? "segment segment--active" : "segment"}
                        key={status || "unmarked"}
                        onClick={() => setStatuses((current) => ({ ...current, [student.student_profile_id]: status }))}
                        type="button"
                      >
                        {status || "unmarked"}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          <button className="button button--primary" disabled={!selectedRecords.length || confirm.isPending || confirmed} onClick={() => confirm.mutate()} type="button">
            {confirm.isPending ? "Confirming..." : "Confirm reviewed attendance"}
          </button>
          <p className="helper-text">Unmarked students are not saved as absent.</p>
          {confirmed ? <p className="success-message" role="status">Reviewed attendance saved.</p> : null}
          {confirm.error ? <p className="error-message" role="alert">{apiErrorMessage(confirm.error)}</p> : null}
          {roster.isPending || confirm.isPending ? <SlowRequestNotice /> : null}
        </div>
      ) : null}
    </section>
  );
}
