import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { announcementsApi } from "../api/announcements";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import type { Announcement, AnnouncementAudience } from "../types/domain";

interface AnnouncementFormValues {
  title: string;
  content: string;
  audience: AnnouncementAudience;
  classroom_ids: string;
}

const announcementSchema = z.object({
  title: z.string().trim().min(1, "Title is required.").max(200),
  content: z.string().trim().min(1, "Content is required.").max(5000),
  audience: z.enum(["all", "classroom", "teacher", "student"]),
  classroom_ids: z.string(),
}).superRefine((value, context) => {
  const ids = value.classroom_ids.split(",").map((item) => item.trim()).filter(Boolean);
  if (value.audience === "classroom" && ids.length === 0) {
    context.addIssue({ code: "custom", message: "Add at least one classroom UUID.", path: ["classroom_ids"] });
  }
  for (const id of ids) {
    if (!z.string().uuid().safeParse(id).success) {
      context.addIssue({ code: "custom", message: "Every classroom ID must be a valid UUID.", path: ["classroom_ids"] });
      break;
    }
  }
});

const emptyValues: AnnouncementFormValues = { title: "", content: "", audience: "all", classroom_ids: "" };

export function AnnouncementsPage({ canManage = false }: { canManage?: boolean }) {
  const client = useQueryClient();
  const [editing, setEditing] = useState<Announcement | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const form = useForm<AnnouncementFormValues>({ defaultValues: emptyValues });
  const list = useQuery({ queryKey: queryKeys.announcements, queryFn: () => announcementsApi.list(canManage) });
  const mutation = useMutation({
    mutationFn: async (values: AnnouncementFormValues) => {
      if (editing) return announcementsApi.update(editing.id, { title: values.title.trim(), content: values.content.trim() });
      const classroomIds = values.classroom_ids.split(",").map((item) => item.trim()).filter(Boolean);
      return announcementsApi.create({ title: values.title.trim(), content: values.content.trim(), audience: values.audience, classroom_ids: classroomIds });
    },
    onSuccess: async () => {
      setEditing(null);
      setNotice("Announcement saved.");
      form.reset(emptyValues);
      await client.invalidateQueries({ queryKey: queryKeys.announcements });
    },
  });
  const deactivate = useMutation({
    mutationFn: announcementsApi.deactivate,
    onSuccess: async () => {
      setNotice("Announcement deactivated.");
      await client.invalidateQueries({ queryKey: queryKeys.announcements });
    },
  });

  const submit = form.handleSubmit((values) => {
    setNotice(null);
    const parsed = announcementSchema.safeParse(values);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) form.setError(String(issue.path[0]) as keyof AnnouncementFormValues, { message: issue.message });
      return;
    }
    mutation.mutate(values);
  });

  const beginEdit = (item: Announcement) => {
    setEditing(item);
    setNotice(null);
    form.reset({ title: item.title, content: item.content, audience: item.audience, classroom_ids: item.classroom_ids.join(", ") });
  };

  return (
    <section className="page-stack">
      <div className="page-heading"><p className="eyebrow">Communication</p><h1>Announcements</h1><p>View the active notices available to your role and classroom scope.</p></div>
      {canManage ? (
        <form className="form-card" onSubmit={submit} noValidate>
          <h2>{editing ? "Edit announcement" : "Publish announcement"}</h2>
          <div className="form-grid">
            <label className="field"><span>Title</span><input {...form.register("title")} />{form.formState.errors.title?.message ? <small className="field-error">{form.formState.errors.title.message}</small> : null}</label>
            <label className="field"><span>Audience</span><select disabled={Boolean(editing)} {...form.register("audience")}><option value="all">All</option><option value="classroom">Classroom</option><option value="teacher">Teachers</option><option value="student">Students</option></select></label>
            <label className="field field--wide"><span>Classroom UUIDs (comma separated)</span><input disabled={Boolean(editing)} {...form.register("classroom_ids")} />{form.formState.errors.classroom_ids?.message ? <small className="field-error">{form.formState.errors.classroom_ids.message}</small> : null}</label>
            <label className="field field--wide"><span>Content</span><textarea rows={5} {...form.register("content")} />{form.formState.errors.content?.message ? <small className="field-error">{form.formState.errors.content.message}</small> : null}</label>
          </div>
          <div className="button-row"><button className="button button--primary" disabled={mutation.isPending} type="submit">{mutation.isPending ? "Saving..." : editing ? "Save changes" : "Publish"}</button>{editing ? <button className="button button--quiet" onClick={() => { setEditing(null); form.reset(emptyValues); }} type="button">Cancel</button> : null}</div>
          {mutation.error ? <p className="error-message" role="alert">{apiErrorMessage(mutation.error)}</p> : null}
        </form>
      ) : null}
      {notice ? <p className="success-message" role="status">{notice}</p> : null}
      {list.isPending ? <p className="empty-state">Loading announcements...</p> : null}
      {list.error ? <p className="error-message" role="alert">{apiErrorMessage(list.error)}</p> : null}
      {list.data?.items.length === 0 ? <p className="empty-state">No announcements are available.</p> : null}
      <div className="card-grid">
        {list.data?.items.map((item) => (
          <article className="content-card compact-card" key={item.id}>
            <p className="eyebrow">{item.audience}</p><h2>{item.title}</h2><p className="preserve-lines">{item.content}</p>
            {canManage ? <div className="button-row"><button className="text-button" onClick={() => beginEdit(item)} type="button">Edit</button>{item.is_active ? <button className="text-button text-button--danger" onClick={() => { if (window.confirm("Deactivate this announcement?")) deactivate.mutate(item.id); }} type="button">Deactivate</button> : <span>Inactive</span>}</div> : null}
          </article>
        ))}
      </div>
      {deactivate.error ? <p className="error-message" role="alert">{apiErrorMessage(deactivate.error)}</p> : null}
    </section>
  );
}
