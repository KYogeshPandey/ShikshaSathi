import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { ApiError } from "../api/client";
import type { Page } from "../types/domain";
import { SlowRequestNotice } from "./SlowRequestNotice";

export type CrudFormValues = Record<string, string>;

export interface CrudField {
  name: string;
  label: string;
  type?: "text" | "time" | "select";
  placeholder?: string;
  createOnly?: boolean;
  options?: ReadonlyArray<{ label: string; value: string }>;
}

export interface CrudColumn<Item> {
  label: string;
  render(item: Item): ReactNode;
}

interface CrudItem {
  id: string;
  is_active: boolean;
}

interface AdminCrudPageProps<Item extends CrudItem> {
  title: string;
  description: string;
  formTitle?: string;
  listTitle?: string;
  listEnabled?: boolean;
  listPrompt?: string;
  paginationKey?: string;
  viewControls?: ReactNode;
  queryKey: QueryKey;
  fields: readonly CrudField[];
  columns: ReadonlyArray<CrudColumn<Item>>;
  emptyValues: CrudFormValues;
  schema: z.ZodType<unknown>;
  load(offset: number): Promise<Page<Item>>;
  create(values: CrudFormValues): Promise<Item>;
  update(id: string, values: CrudFormValues): Promise<Item>;
  deactivate(id: string): Promise<Item>;
  toFormValues(item: Item): CrudFormValues;
}

type MutationCommand<Item> =
  | { kind: "create"; values: CrudFormValues }
  | { kind: "update"; item: Item; values: CrudFormValues }
  | { kind: "deactivate"; item: Item };

function errorMessage(error: Error | null): string | null {
  if (!error) return null;
  if (error instanceof ApiError) return error.message;
  return "The request could not be completed.";
}

export function AdminCrudPage<Item extends CrudItem>({
  title,
  description,
  formTitle,
  listTitle = "Current records",
  listEnabled = true,
  listPrompt = "Choose a classroom to view records.",
  paginationKey,
  viewControls,
  queryKey,
  fields,
  columns,
  emptyValues,
  schema,
  load,
  create,
  update,
  deactivate,
  toFormValues,
}: AdminCrudPageProps<Item>) {
  const queryClient = useQueryClient();
  const [pagination, setPagination] = useState({ key: paginationKey, offset: 0 });
  const offset = pagination.key === paginationKey ? pagination.offset : 0;
  const setOffset = (nextOffset: number) => {
    setPagination({ key: paginationKey, offset: nextOffset });
  };
  const [editing, setEditing] = useState<Item | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const form = useForm<CrudFormValues>({ defaultValues: emptyValues });
  const listQuery = useQuery({
    queryKey: [...queryKey, offset],
    queryFn: () => load(offset),
    enabled: listEnabled,
  });
  const mutation = useMutation({
    mutationFn: async (command: MutationCommand<Item>) => {
      if (command.kind === "create") return create(command.values);
      if (command.kind === "update") return update(command.item.id, command.values);
      return deactivate(command.item.id);
    },
    onSuccess: async (_item, command) => {
      setNotice(command.kind === "deactivate" ? "Record deactivated." : "Changes saved.");
      setEditing(null);
      form.reset(emptyValues);
      await queryClient.invalidateQueries({ queryKey });
    },
  });

  const submit = form.handleSubmit((values) => {
    setNotice(null);
    const parsed = schema.safeParse(values);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        const field = String(issue.path[0] ?? "form");
        form.setError(field, { message: issue.message, type: issue.code });
      }
      return;
    }
    mutation.mutate(
      editing ? { kind: "update", item: editing, values } : { kind: "create", values },
    );
  });

  const requestDeactivate = (item: Item) => {
    if (window.confirm(`Deactivate this ${title.toLowerCase()} record?`)) {
      mutation.mutate({ kind: "deactivate", item });
    }
  };

  const page = listQuery.data;
  const hasNext = page ? offset + page.limit < page.total : false;

  return (
    <section className="page-stack" aria-labelledby="resource-heading">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Administration</p>
          <h1 id="resource-heading">{title}</h1>
          <p>{description}</p>
        </div>
      </div>

      {viewControls}

      <form className="form-card" onSubmit={submit} noValidate>
        <h2>{editing ? `Edit ${title}` : formTitle ?? `Add ${title}`}</h2>
        <div className="form-grid">
          {fields.map((field) => {
            const disabled = mutation.isPending || Boolean(editing && field.createOnly);
            const error = form.formState.errors[field.name]?.message;
            const errorId = `${field.name}-error`;
            return (
              <label className="field" key={field.name}>
                <span>{field.label}</span>
                {field.type === "select" ? (
                  <select aria-describedby={error ? errorId : undefined} aria-invalid={Boolean(error)} disabled={disabled} {...form.register(field.name)}>
                    {field.options?.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    disabled={disabled}
                    placeholder={field.placeholder}
                    type={field.type ?? "text"}
                    aria-describedby={error ? errorId : undefined}
                    aria-invalid={Boolean(error)}
                    {...form.register(field.name)}
                  />
                )}
                {error ? (
                  <small className="field-error" id={errorId}>{error}</small>
                ) : null}
              </label>
            );
          })}
        </div>
        <div className="button-row">
          <button className="button" disabled={mutation.isPending} type="submit">
            {mutation.isPending ? "Saving…" : editing ? "Save changes" : "Create"}
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
        {notice ? <p className="success-message" role="status">{notice}</p> : null}
        {mutation.error ? <p className="error-message" role="alert">{errorMessage(mutation.error)}</p> : null}
        {mutation.isPending ? <SlowRequestNotice /> : null}
      </form>

      <div className="table-card">
        <div className="table-card__header">
          <h2>{listTitle}</h2>
          {page ? <span>{page.total} total</span> : null}
        </div>
        {!listEnabled ? <p className="empty-state">{listPrompt}</p> : null}
        {listQuery.isPending ? <p className="empty-state">Loading records…</p> : null}
        {listQuery.isPending ? <SlowRequestNotice /> : null}
        {listQuery.error ? <p className="error-message" role="alert">{errorMessage(listQuery.error)}</p> : null}
        {page && page.items.length === 0 ? <p className="empty-state">No records found.</p> : null}
        {page && page.items.length > 0 ? (
          <div className="table-scroll" role="region" aria-label={`${title} records table`} tabIndex={0}>
            <table>
              <thead><tr>{columns.map((column) => <th key={column.label}>{column.label}</th>)}<th>Actions</th></tr></thead>
              <tbody>
                {page.items.map((item) => (
                  <tr key={item.id}>
                    {columns.map((column) => <td key={column.label}>{column.render(item)}</td>)}
                    <td>
                      <div className="table-actions">
                        <button
                          className="text-button"
                          onClick={() => {
                            setEditing(item);
                            form.reset(toFormValues(item));
                          }}
                          type="button"
                        >
                          Edit
                        </button>
                        {item.is_active ? (
                          <button className="text-button text-button--danger" onClick={() => requestDeactivate(item)} type="button">Deactivate</button>
                        ) : <span>Inactive</span>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {listEnabled ? <div className="pagination">
          <button className="button button--quiet" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))} type="button">Previous</button>
          <button className="button button--quiet" disabled={!hasNext} onClick={() => setOffset(offset + 100)} type="button">Next</button>
        </div> : null}
      </div>
    </section>
  );
}
