import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { academicsApi } from "../api/academics";
import { announcementsApi } from "../api/announcements";
import { apiErrorMessage } from "../api/errorMessage";
import { queryKeys } from "../api/queryKeys";
import { SlowRequestNotice } from "../components/SlowRequestNotice";
import type { Announcement, AnnouncementAudience } from "../types/domain";

interface AnnouncementFormValues {
  title: string;
  content: string;
  audience: AnnouncementAudience;
  classroom_ids: string[];
}

const announcementSchema = z
  .object({
    title: z.string().trim().min(1, "Title is required.").max(200),
    content: z.string().trim().min(1, "Content is required.").max(5000),
    audience: z.enum(["all", "classroom", "teacher", "student"]),
    classroom_ids: z.array(z.string().uuid()),
  })
  .superRefine((value, context) => {
    if (value.audience === "classroom" && value.classroom_ids.length === 0) {
      context.addIssue({
        code: "custom",
        message: "Choose at least one classroom.",
        path: ["classroom_ids"],
      });
    }
    if (value.audience !== "classroom" && value.classroom_ids.length > 0) {
      context.addIssue({
        code: "custom",
        message: "Classrooms can only be selected for a classroom audience.",
        path: ["classroom_ids"],
      });
    }
  });

const emptyValues: AnnouncementFormValues = {
  title: "",
  content: "",
  audience: "all",
  classroom_ids: [],
};

const audienceLabels: Record<Exclude<AnnouncementAudience, "classroom">, string> = {
  all: "All school",
  teacher: "Teachers",
  student: "Students",
};

export function AnnouncementsPage({ canManage = false }: { canManage?: boolean }) {
  const client = useQueryClient();
  const [editing, setEditing] = useState<Announcement | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const form = useForm<AnnouncementFormValues>({ defaultValues: emptyValues });
  const audience = useWatch({ control: form.control, name: "audience" });
  const list = useQuery({
    queryKey: queryKeys.announcements,
    queryFn: () => announcementsApi.list(canManage),
  });
  const classrooms = useQuery({
    queryKey: [...queryKeys.classrooms, "announcement-targets"],
    queryFn: () => academicsApi.listClassrooms({ includeInactive: true }),
    enabled: canManage,
  });
  const classroomNames = new Map(
    classrooms.data?.items.map((classroom) => [classroom.id, classroom.name]) ?? [],
  );
  const activeClassrooms = classrooms.data?.items.filter((classroom) => classroom.is_active) ?? [];

  const mutation = useMutation({
    mutationFn: async (values: AnnouncementFormValues) => {
      if (editing) {
        return announcementsApi.update(editing.id, {
          title: values.title.trim(),
          content: values.content.trim(),
        });
      }
      return announcementsApi.create({
        title: values.title.trim(),
        content: values.content.trim(),
        audience: values.audience,
        classroom_ids: values.audience === "classroom" ? values.classroom_ids : [],
      });
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
      for (const issue of parsed.error.issues) {
        form.setError(String(issue.path[0]) as keyof AnnouncementFormValues, {
          message: issue.message,
        });
      }
      return;
    }
    mutation.mutate(parsed.data);
  });

  const beginEdit = (item: Announcement) => {
    setEditing(item);
    setNotice(null);
    form.reset({
      title: item.title,
      content: item.content,
      audience: item.audience,
      classroom_ids: item.classroom_ids,
    });
  };

  const audienceLabel = (item: Announcement): string => {
    if (item.audience !== "classroom") return audienceLabels[item.audience];
    const names = item.classroom_ids.map((id) => classroomNames.get(id)).filter(Boolean);
    return names.length ? names.join(", ") : "Specific classrooms";
  };

  return (
    <section className="page-stack">
      <div className="page-heading">
        <p className="eyebrow">Communication</p>
        <h1>Announcements</h1>
        <p>View the active notices available to your role and classroom scope.</p>
      </div>
      {canManage ? (
        <form className="form-card" onSubmit={submit} noValidate>
          <h2>{editing ? "Edit announcement" : "Publish announcement"}</h2>
          <div className="form-grid">
            <label className="field">
              <span>Title</span>
              <input
                aria-describedby={form.formState.errors.title ? "announcement-title-error" : undefined}
                aria-invalid={Boolean(form.formState.errors.title)}
                {...form.register("title")}
              />
              {form.formState.errors.title?.message ? (
                <small className="field-error" id="announcement-title-error">
                  {form.formState.errors.title.message}
                </small>
              ) : null}
            </label>
            <label className="field">
              <span>Audience</span>
              <select disabled={Boolean(editing)} {...form.register("audience")}>
                <option value="all">All</option>
                <option value="teacher">Teachers</option>
                <option value="student">Students</option>
                <option value="classroom">Specific classroom(s)</option>
              </select>
            </label>
            {audience === "classroom" ? (
              <fieldset className="field field--wide classroom-selector" disabled={Boolean(editing)}>
                <legend>Classrooms</legend>
                {classrooms.isPending ? <p>Loading classrooms…</p> : null}
                {classrooms.error ? (
                  <p className="error-message" role="alert">{apiErrorMessage(classrooms.error)}</p>
                ) : null}
                {activeClassrooms.length === 0 && !classrooms.isPending ? (
                  <p className="empty-state">No classrooms available. Create a classroom first.</p>
                ) : null}
                <div className="checkbox-grid">
                  {activeClassrooms.map((classroom) => (
                    <label className="checkbox-option" key={classroom.id}>
                      <input
                        type="checkbox"
                        value={classroom.id}
                        {...form.register("classroom_ids")}
                      />
                      <span>{classroom.name}</span>
                    </label>
                  ))}
                </div>
                {form.formState.errors.classroom_ids?.message ? (
                  <small className="field-error">{form.formState.errors.classroom_ids.message}</small>
                ) : null}
              </fieldset>
            ) : null}
            <label className="field field--wide">
              <span>Content</span>
              <textarea
                aria-describedby={form.formState.errors.content ? "announcement-content-error" : undefined}
                aria-invalid={Boolean(form.formState.errors.content)}
                rows={5}
                {...form.register("content")}
              />
              {form.formState.errors.content?.message ? (
                <small className="field-error" id="announcement-content-error">
                  {form.formState.errors.content.message}
                </small>
              ) : null}
            </label>
          </div>
          <div className="button-row">
            <button className="button button--primary" disabled={mutation.isPending} type="submit">
              {mutation.isPending ? "Saving…" : editing ? "Save changes" : "Publish"}
            </button>
            {editing ? (
              <button
                className="button button--quiet"
                onClick={() => {
                  setEditing(null);
                  form.reset(emptyValues);
                }}
                type="button"
              >
                Cancel
              </button>
            ) : null}
          </div>
          {mutation.error ? (
            <p className="error-message" role="alert">{apiErrorMessage(mutation.error)}</p>
          ) : null}
          {mutation.isPending ? <SlowRequestNotice /> : null}
        </form>
      ) : null}
      {notice ? <p className="success-message" role="status">{notice}</p> : null}
      {list.isPending ? <p className="empty-state">Loading announcements…</p> : null}
      {list.isPending ? <SlowRequestNotice /> : null}
      {list.error ? <p className="error-message" role="alert">{apiErrorMessage(list.error)}</p> : null}
      {list.data?.items.length === 0 ? (
        <p className="empty-state">No announcements are available.</p>
      ) : null}
      <div className="card-grid">
        {list.data?.items.map((item) => (
          <article className="content-card compact-card" key={item.id}>
            <p className="eyebrow">{audienceLabel(item)}</p>
            <h2>{item.title}</h2>
            <p className="preserve-lines">{item.content}</p>
            {canManage ? (
              <div className="button-row">
                <button className="text-button" onClick={() => beginEdit(item)} type="button">
                  Edit
                </button>
                {item.is_active ? (
                  <button
                    className="text-button text-button--danger"
                    disabled={deactivate.isPending}
                    onClick={() => {
                      if (window.confirm("Deactivate this announcement?")) {
                        deactivate.mutate(item.id);
                      }
                    }}
                    type="button"
                  >
                    {deactivate.isPending && deactivate.variables === item.id
                      ? "Deactivating…"
                      : "Deactivate"}
                  </button>
                ) : (
                  <span>Inactive</span>
                )}
              </div>
            ) : null}
          </article>
        ))}
      </div>
      {deactivate.isPending ? <SlowRequestNotice /> : null}
      {deactivate.error ? (
        <p className="error-message" role="alert">{apiErrorMessage(deactivate.error)}</p>
      ) : null}
    </section>
  );
}
