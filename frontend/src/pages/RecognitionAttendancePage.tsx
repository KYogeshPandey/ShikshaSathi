import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { academicsApi } from "../api/academics";
import { attendanceApi } from "../api/attendance";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { SlowRequestNotice } from "../components/SlowRequestNotice";
import { recognitionApi } from "../api/recognition";
import type { RecognitionAttendanceAttempt } from "../types/domain";

const decisionLabels: Record<RecognitionAttendanceAttempt["decision"], string> = {
  found: "Match found",
  unknown: "Confirmation needed",
  ambiguous: "Multiple possible matches",
};

interface RecognitionScopeValues {
  classroom_id: string;
  subject_id: string;
  attendance_date: string;
}

const recognitionSchema = z.object({
  classroom_id: z.string().uuid("Choose a classroom."),
  subject_id: z.string().uuid("Choose a subject."),
  attendance_date: z.string().date("Choose a valid date."),
});

function localDate(): string {
  const date = new Date();
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

export function RecognitionAttendancePage() {
  const client = useQueryClient();
  const form = useForm<RecognitionScopeValues>({ defaultValues: { classroom_id: "", subject_id: "", attendance_date: localDate() } });
  const [file, setFile] = useState<File | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isCameraOn, setIsCameraOn] = useState(false);
  const [attempt, setAttempt] = useState<RecognitionAttendanceAttempt | null>(null);
  const [confirmationId, setConfirmationId] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const classrooms = useQuery({ queryKey: queryKeys.classrooms, queryFn: () => academicsApi.listClassrooms() });
  const subjects = useQuery({ queryKey: queryKeys.subjects, queryFn: () => academicsApi.listSubjects() });
  const optionsLoading = classrooms.isPending || subjects.isPending;

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setIsCameraOn(false);
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  const startCamera = async () => {
    setCameraError(null);
    stopCamera();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
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
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
    if (!blob) {
      setCameraError("The camera image could not be captured.");
      return;
    }
    setFile(new File([blob], `attendance-${Date.now()}.jpg`, { type: "image/jpeg" }));
    stopCamera();
  };

  const createAttempt = useMutation({
    mutationFn: ({ values, image }: { values: RecognitionScopeValues; image: File }) => recognitionApi.createAttempt({ classroomId: values.classroom_id, subjectId: values.subject_id, attendanceDate: values.attendance_date, file: image }),
    onSuccess: async (result) => {
      setAttempt(result);
      setConfirmed(false);
      setConfirmationId("");
      if (result.decision === "found") await client.invalidateQueries({ queryKey: queryKeys.attendance });
    },
  });

  const roster = useQuery({
    queryKey: attempt ? queryKeys.attendanceRoster(attempt.classroom_id, attempt.subject_id) : [...queryKeys.attendance, "roster", "recognition-idle"],
    queryFn: () => attendanceApi.getRoster({ classroomId: attempt!.classroom_id, subjectId: attempt!.subject_id }),
    enabled: Boolean(attempt?.requires_confirmation),
  });
  const confirm = useMutation({
    mutationFn: () => recognitionApi.confirm(attempt!.attempt_id, confirmationId),
    onSuccess: async () => {
      setConfirmed(true);
      await client.invalidateQueries({ queryKey: queryKeys.attendance });
    },
  });

  const submit = form.handleSubmit((values) => {
    createAttempt.reset();
    setAttempt(null);
    const parsed = recognitionSchema.safeParse(values);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) form.setError(issue.path[0] as keyof RecognitionScopeValues, { message: issue.message });
      return;
    }
    if (!file) {
      form.setError("root", { message: "Capture or choose an image before submitting." });
      return;
    }
    form.clearErrors("root");
    createAttempt.mutate({ values: parsed.data, image: file });
  });

  return (
    <section className="page-stack">
      <div className="page-heading"><p className="eyebrow">Teacher attendance</p><h1>Recognition attendance</h1><p>Capture or upload one image. Matches are recorded automatically; uncertain results ask you to confirm from the assigned class roster.</p></div>
      <form className="form-card" onSubmit={submit} noValidate>
        <div className="form-grid">
          <label className="field"><span>Classroom</span><select aria-describedby={form.formState.errors.classroom_id ? "recognition-classroom-error" : undefined} aria-invalid={Boolean(form.formState.errors.classroom_id)} disabled={optionsLoading} {...form.register("classroom_id")}><option value="">Select classroom</option>{classrooms.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.code})</option>)}</select>{form.formState.errors.classroom_id?.message ? <small className="field-error" id="recognition-classroom-error">{form.formState.errors.classroom_id.message}</small> : null}</label>
          <label className="field"><span>Subject</span><select aria-describedby={form.formState.errors.subject_id ? "recognition-subject-error" : undefined} aria-invalid={Boolean(form.formState.errors.subject_id)} disabled={optionsLoading} {...form.register("subject_id")}><option value="">Select subject</option>{subjects.data?.items.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.code})</option>)}</select>{form.formState.errors.subject_id?.message ? <small className="field-error" id="recognition-subject-error">{form.formState.errors.subject_id.message}</small> : null}</label>
          <label className="field"><span>Date</span><input aria-describedby={form.formState.errors.attendance_date ? "recognition-date-error" : undefined} aria-invalid={Boolean(form.formState.errors.attendance_date)} type="date" {...form.register("attendance_date")} />{form.formState.errors.attendance_date?.message ? <small className="field-error" id="recognition-date-error">{form.formState.errors.attendance_date.message}</small> : null}</label>
          <label className="field"><span>Image file fallback</span><input accept="image/jpeg,image/png,image/webp" onChange={(event) => setFile(event.target.files?.[0] ?? null)} type="file" /></label>
        </div>
        <div className="camera-panel"><video aria-label="Camera preview" muted playsInline ref={videoRef} /><div className="button-row"><button className="button button--quiet" onClick={startCamera} type="button">Start camera</button><button className="button button--quiet" disabled={!isCameraOn} onClick={capture} type="button">Capture image</button><button className="button button--quiet" disabled={!isCameraOn} onClick={stopCamera} type="button">Stop camera</button></div>{file ? <p>Ready: {file.name}</p> : null}{cameraError ? <p className="error-message" role="alert">{cameraError}</p> : null}</div>
        <button className="button button--primary" disabled={optionsLoading || createAttempt.isPending} type="submit">{optionsLoading ? "Loading options…" : createAttempt.isPending ? "Checking…" : "Submit recognition attempt"}</button>
        {optionsLoading || createAttempt.isPending ? <SlowRequestNotice /> : null}
        {form.formState.errors.root?.message ? <p className="error-message" role="alert">{form.formState.errors.root.message}</p> : null}
        {createAttempt.error ? <p className="error-message" role="alert">{apiErrorMessage(createAttempt.error)}</p> : null}
      </form>
      {attempt ? (
        <div className="content-card compact-card" aria-live="polite">
          <p className="eyebrow">Recognition result</p><h2>{decisionLabels[attempt.decision]}</h2>
          {attempt.decision === "found" ? <p className="success-message">Attendance was recorded automatically.</p> : <p>Select a student from the active roster for this assigned classroom.</p>}
          {attempt.requires_confirmation ? (
            <div className="form-grid"><label className="field"><span>Confirm student</span><select onChange={(event) => setConfirmationId(event.target.value)} value={confirmationId}><option value="">Select roster student</option>{roster.data?.map((student) => <option key={student.student_profile_id} value={student.student_profile_id}>Roll {student.roll_number ?? "not assigned"}</option>)}</select></label><button className="button button--primary" disabled={!confirmationId || confirm.isPending} onClick={() => confirm.mutate()} type="button">{confirm.isPending ? "Confirming..." : "Confirm attendance"}</button></div>
          ) : null}
          {roster.isPending ? <p>Loading class roster...</p> : null}{roster.error ? <p className="error-message" role="alert">{apiErrorMessage(roster.error)}</p> : null}{confirmed ? <p className="success-message" role="status">Attendance confirmation saved.</p> : null}{confirm.error ? <p className="error-message" role="alert">{apiErrorMessage(confirm.error)}</p> : null}
          {roster.isPending || confirm.isPending ? <SlowRequestNotice /> : null}
        </div>
      ) : null}
    </section>
  );
}
