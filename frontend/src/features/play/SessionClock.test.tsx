import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SessionClock, bannerFor, clock } from "./SessionClock";

describe("bannerFor", () => {
  it("is silent while there is time, warns at 5 and 1 minutes and says when time is up", () => {
    expect(bannerFor(601, 20)).toBeNull();
    expect(bannerFor(300, 20)).toMatch(/^5 minutes left/);
    expect(bannerFor(61, 20)).toMatch(/^5 minutes left/);
    expect(bannerFor(60, 20)).toMatch(/^1 minute left/);
    expect(bannerFor(0, 20)).toMatch(/^Time is up/);
  });

  it("skips a warning at or beyond the scenario's whole length", () => {
    expect(bannerFor(240, 5)).toBeNull(); // a 5-minute scenario has no 5-minute warning
    expect(bannerFor(60, 5)).toMatch(/^1 minute left/);
    expect(bannerFor(30, 1)).toBeNull();
  });

  it("uses the scenario's own warning times and says what time-out will do", () => {
    expect(bannerFor(170, 20, [3])).toMatch(/^3 minutes left/);
    expect(bannerFor(250, 20, [3])).toBeNull(); // the default 5 does not apply
    expect(bannerFor(0, 20, [3], "end")).toBe("Time is up. The meeting is ending.");
    expect(bannerFor(0, 20, [3], "fail")).toBe("Time is up. The meeting ends without an agreement.");
    expect(bannerFor(0, 20, [3], "guide")).toMatch(/does not end by itself/);
    expect(bannerFor(0, 20, [3], "trainer")).toBe("Time is up. Your trainer decides how this ends.");
  });

  it("formats minutes and seconds", () => {
    expect(clock(594)).toBe("9:54");
    expect(clock(5)).toBe("0:05");
  });
});

describe("SessionClock", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("counts down from what the server said, shows the warning and stops at zero", async () => {
    render(<SessionClock secondsLeft={302} minutesTotal={10} />);
    expect(screen.getByRole("timer")).toHaveTextContent("5:02");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByRole("timer")).toHaveTextContent("4:59");
    expect(screen.getByRole("status")).toHaveTextContent("5 minutes left");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400_000);
    });
    expect(screen.getByRole("timer")).toHaveTextContent("0:00");
    expect(screen.getByRole("status")).toHaveTextContent("Time is up");
  });

  it("starts again from the server's figure when the session reloads", async () => {
    const { rerender } = render(<SessionClock secondsLeft={100} minutesTotal={10} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(screen.getByRole("timer")).toHaveTextContent("1:30");
    rerender(<SessionClock secondsLeft={200} minutesTotal={10} />);
    expect(screen.getByRole("timer")).toHaveTextContent("3:20");
  });

  it("tells the page once when the clock reaches zero", async () => {
    const expired = vi.fn();
    render(<SessionClock secondsLeft={3} minutesTotal={10} onExpire={expired} />);
    expect(expired).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it("tells the page at once when it opens with no time left", () => {
    const expired = vi.fn();
    render(<SessionClock secondsLeft={0} minutesTotal={10} onExpire={expired} />);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it("shows nothing without a time from the server", () => {
    const { container } = render(<SessionClock secondsLeft={null} minutesTotal={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
