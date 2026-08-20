import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { apiErrorMessage } from "../api/errorMessage";
import { importsApi } from "../api/imports";
import { SlowRequestNotice } from "../components/SlowRequestNotice";
import type { BulkImportEntity } from "../types/domain";

const MAX_IMPORT_BYTES = 2 * 1024 * 1024;
const importSchema = z.object({
  entity: z.enum(["classrooms", "subjects", "teacher-profiles", "student-profiles"]),
});

interface ImportFormValues {
  entity: BulkImportEntity;
}

export function AdminImportsPage() {
  const form = useForm<ImportFormValues>({ defaultValues: { entity: "classrooms" } });
  const mutation = useMutation({ mutationFn: ({ entity, file }: { entity: BulkImportEntity; file: File }) => importsApi.upload(entity, file) });

  const submit = form.handleSubmit((values, event) => {
    mutation.reset();
    const parsed = importSchema.safeParse(values);
    if (!parsed.success) return;
    const input = (event?.currentTarget as HTMLFormElement | undefined)?.querySelector<HTMLInputElement>('input[type="file"]');
    const file = input?.files?.[0];
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
    form.clearErrors("root");
    mutation.mutate({ entity: values.entity, file });
  });

  return (
    <section className="page-stack">
      <div className="page-heading">
        <p className="eyebrow">Administration</p>
        <h1>Bulk imports</h1>
        <p>Upload at most 500 classroom, subject, teacher-profile, or student-profile rows per CSV/XLSX file.</p>
      </div>
      <form className="form-card" onSubmit={submit} noValidate>
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
          <label className="field">
            <span>CSV or XLSX file</span>
            <input accept=".csv,.xlsx" type="file" />
          </label>
        </div>
        <button className="button button--primary" disabled={mutation.isPending} type="submit">
          {mutation.isPending ? "Importing..." : "Run import"}
        </button>
        {form.formState.errors.root?.message ? <p className="error-message" role="alert">{form.formState.errors.root.message}</p> : null}
        {mutation.error ? <p className="error-message" role="alert">{apiErrorMessage(mutation.error)}</p> : null}
        {mutation.isPending ? <SlowRequestNotice /> : null}
      </form>
      {mutation.data ? (
        <div className="table-card" aria-live="polite">
          <h2>Import result</h2>
          <p>{mutation.data.imported_count} imported; {mutation.data.failed_count} failed out of {mutation.data.total_rows} rows.</p>
          {mutation.data.errors.length ? (
            <div className="table-scroll" role="region" aria-label="Import row errors" tabIndex={0}><table><thead><tr><th>Row</th><th>Code</th><th>Message</th></tr></thead><tbody>
              {mutation.data.errors.map((error) => <tr key={`${error.row_number}-${error.code}`}><td>{error.row_number}</td><td>{error.code}</td><td>{error.message}</td></tr>)}
            </tbody></table></div>
          ) : <p className="success-message">The import completed without row errors.</p>}
        </div>
      ) : null}
    </section>
  );
}
