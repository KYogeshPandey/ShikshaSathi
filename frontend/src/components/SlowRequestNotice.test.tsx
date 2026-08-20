import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SLOW_REQUEST_NOTICE_DELAY_MS, SlowRequestNotice } from "./SlowRequestNotice";

afterEach(() => vi.useRealTimers());

describe("SlowRequestNotice", () => {
  it("only explains a server wake-up after a request has remained pending", () => {
    vi.useFakeTimers();
    const view = render(<SlowRequestNotice />);

    act(() => vi.advanceTimersByTime(SLOW_REQUEST_NOTICE_DELAY_MS - 1));
    expect(screen.queryByText(/server is waking up/i)).not.toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByRole("status")).toHaveTextContent(/server is waking up/i);

    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
