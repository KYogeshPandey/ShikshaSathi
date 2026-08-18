import { apiClient } from "./client";
import type { BulkImportEntity, BulkImportResult } from "../types/domain";

export const importsApi = {
  upload(entity: BulkImportEntity, file: File): Promise<BulkImportResult> {
    const form = new FormData();
    form.set("file", file);
    return apiClient.post<BulkImportResult>(`/imports/${entity}`, form);
  },
};
