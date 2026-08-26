import { apiClient } from "./client";
import type {
  BulkImportEntity,
  BulkImportResult,
  StudentOnboardingResult,
} from "../types/domain";

export const importsApi = {
  upload(entity: BulkImportEntity, file: File): Promise<BulkImportResult> {
    const form = new FormData();
    form.set("file", file);
    return apiClient.post<BulkImportResult>(`/imports/${entity}`, form);
  },
  onboard(
    classroomId: string,
    studentsFile: File,
    photosZip?: File,
    updateExisting = false,
  ): Promise<StudentOnboardingResult> {
    const form = new FormData();
    form.set("classroom_id", classroomId);
    form.set("students_file", studentsFile);
    form.set("update_existing", String(updateExisting));
    if (photosZip) form.set("photos_zip", photosZip);
    return apiClient.post<StudentOnboardingResult>("/student-onboarding", form);
  },
};
