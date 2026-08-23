import { apiClient } from "./client";
import type {
  RecognitionAttendanceAttempt,
  RecognitionAttendanceConfirmation,
  RecognitionAttendanceReview,
  RecognitionAttendanceReviewConfirmation,
  AttendanceStatus,
} from "../types/domain";

export interface RecognitionAttemptInput {
  classroomId: string;
  subjectId: string;
  attendanceDate: string;
  file: File;
}

export const recognitionApi = {
  createAttempt(input: RecognitionAttemptInput): Promise<RecognitionAttendanceAttempt> {
    const form = new FormData();
    form.set("classroom_id", input.classroomId);
    form.set("subject_id", input.subjectId);
    form.set("attendance_date", input.attendanceDate);
    form.set("file", input.file);
    return apiClient.post<RecognitionAttendanceAttempt>(
      "/face-recognition/attendance/attempts",
      form,
    );
  },
  confirm(attemptId: string, studentProfileId: string) {
    return apiClient.post<RecognitionAttendanceConfirmation>(
      `/face-recognition/attendance/attempts/${attemptId}/confirm`,
      { student_profile_id: studentProfileId },
    );
  },
  createReview(input: RecognitionAttemptInput): Promise<RecognitionAttendanceReview> {
    const form = new FormData();
    form.set("classroom_id", input.classroomId);
    form.set("subject_id", input.subjectId);
    form.set("attendance_date", input.attendanceDate);
    form.set("file", input.file);
    return apiClient.post<RecognitionAttendanceReview>(
      "/face-recognition/attendance/reviews",
      form,
    );
  },
  confirmReview(
    reviewId: string,
    records: Array<{ student_profile_id: string; status: AttendanceStatus }>,
  ) {
    return apiClient.post<RecognitionAttendanceReviewConfirmation>(
      `/face-recognition/attendance/reviews/${reviewId}/confirm`,
      { records },
    );
  },
};
