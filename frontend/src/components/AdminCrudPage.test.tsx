import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { z } from "zod";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AdminCrudPage } from "./AdminCrudPage";

interface Item {
  id: string;
  name: string;
  is_active: boolean;
}

const item: Item = { id: "record-1", name: "Original", is_active: true };
const mocks = { load: vi.fn(), create: vi.fn(), update: vi.fn(), deactivate: vi.fn() };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AdminCrudPage<Item>
        title="Records"
        description="Manage records."
        queryKey={["records"]}
        fields={[{ name: "name", label: "Name" }]}
        columns={[{ label: "Name", render: (record) => record.name }]}
        emptyValues={{ name: "" }}
        schema={z.object({ name: z.string().trim().min(1, "Name is required.") })}
        load={mocks.load}
        create={mocks.create}
        update={mocks.update}
        deactivate={mocks.deactivate}
        toFormValues={(record) => ({ name: record.name })}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.load.mockResolvedValue({ items: [item], total: 1, limit: 100, offset: 0 });
  mocks.create.mockResolvedValue({ ...item, id: "record-2", name: "Created" });
  mocks.update.mockResolvedValue({ ...item, name: "Updated" });
  mocks.deactivate.mockResolvedValue({ ...item, is_active: false });
});

describe("AdminCrudPage", () => {
  it("validates, creates, and invalidates the resource list", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Original");

    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("Name is required.")).toBeVisible();
    expect(mocks.create).not.toHaveBeenCalled();

    await user.type(screen.getByRole("textbox"), "Created");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith({ name: "Created" }));
    expect(await screen.findByText("Changes saved.")).toBeVisible();
    await waitFor(() => expect(mocks.load.mock.calls.length).toBeGreaterThan(1));
  });

  it("resets the form for editing and confirms before deactivation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Original");

    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Name")).toHaveValue("Original");
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Updated");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith("record-1", { name: "Updated" }));

    await user.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => expect(mocks.deactivate).toHaveBeenCalledWith("record-1"));
  });
});
