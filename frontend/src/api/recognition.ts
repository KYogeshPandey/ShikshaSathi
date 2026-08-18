import { apiClient } from "./client";
import type {
  RecognitionAttendanceAttempt,
  RecognitionAttendanceConfirmation,
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
};
