import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnnouncementsPage } from "./AnnouncementsPage";

const classroomA = "0ee1c4bc-641c-5fa7-9537-177b97840172";
const classroomB = "1ee1c4bc-641c-5fa7-9537-177b97840173";
const mocks = vi.hoisted(() => ({
  list: vi.fn(), create: vi.fn(), update: vi.fn(), deactivate: vi.fn(), listClassrooms: vi.fn(),
}));
vi.mock("../api/announcements", () => ({ announcementsApi: {
  list: mocks.list, create: mocks.create, update: mocks.update, deactivate: mocks.deactivate,
} }));
vi.mock("../api/academics", () => ({ academicsApi: { listClassrooms: mocks.listClassrooms } }));

function renderPage(canManage = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><AnnouncementsPage canManage={canManage} /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.list.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
  mocks.listClassrooms.mockResolvedValue({
    items: [
      { id: classroomA, name: "AI Section A", code: "AI-A", grade_level: null, section: "A", is_active: true, created_at: "2026-08-01", updated_at: "2026-08-01" },
      { id: classroomB, name: "AI Section B", code: "AI-B", grade_level: null, section: "B", is_active: true, created_at: "2026-08-01", updated_at: "2026-08-01" },
    ],
    total: 2, limit: 100, offset: 0,
  });
  mocks.create.mockImplementation(async (payload) => ({ id: "announcement-id", ...payload, is_active: true, created_at: "2026-08-01", updated_at: "2026-08-01" }));
});

describe("announcement targeting", () => {
  it.each([
    ["All", "all"],
    ["Teachers", "teacher"],
    ["Students", "student"],
  ])("publishes the %s audience using existing semantics", async (label, audience) => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByLabelText("Audience");
    await user.type(screen.getByLabelText("Title"), `${label} notice`);
    await user.selectOptions(screen.getByLabelText("Audience"), audience);
    await user.type(screen.getByLabelText("Content"), "Current notice content");
    await user.click(screen.getByRole("button", { name: "Publish" }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith({
      title: `${label} notice`, content: "Current notice content", audience, classroom_ids: [],
    }));
  });

  it("targets named classrooms and never asks the Admin for raw UUID text", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByLabelText("Audience");
    await user.type(screen.getByLabelText("Title"), "Section notice");
    await user.selectOptions(screen.getByLabelText("Audience"), "classroom");
    expect(await screen.findByLabelText("AI Section A")).toBeVisible();
    expect(screen.getByLabelText("AI Section B")).toBeVisible();
    expect(screen.queryByLabelText(/Classroom UUIDs/i)).not.toBeInTheDocument();
    await user.click(screen.getByLabelText("AI Section A"));
    await user.type(screen.getByLabelText("Content"), "For Section A only");
    await user.click(screen.getByRole("button", { name: "Publish" }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith({
      title: "Section notice", content: "For Section A only", audience: "classroom", classroom_ids: [classroomA],
    }));
  });
});
