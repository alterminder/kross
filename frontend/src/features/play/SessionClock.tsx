import { useEffect, useState } from "react";

/** Minutes left at which a soft banner appears when the scenario names none. Only those shorter than the scenario itself are used. */
export const WARNINGS = [5, 1];

export function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** The banner for the lowest warning the time has crossed, or the time-is-up note. null while there is time. */
export function bannerFor(secondsLeft: number, minutesTotal: number, warnings: number[] = WARNINGS, onTimeout = "guide"): string | null {
  if (secondsLeft <= 0) {
    if (onTimeout === "end") return "Time is up. The meeting is ending.";
    if (onTimeout === "fail") return "Time is up. The meeting ends without an agreement.";
    if (onTimeout === "trainer") return "Time is up. Your trainer decides how this ends.";
    return "Time is up. Wrap up: the meeting does not end by itself.";
  }
  const crossed = warnings.filter((minutes) => minutes < minutesTotal && secondsLeft <= minutes * 60);
  if (crossed.length === 0) return null;
  const minutes = Math.min(...crossed);
  return `${minutes} minute${minutes === 1 ? "" : "s"} left. Steer towards what you can still agree.`;
}

/**
 * Counts down from what the server last said was left (it re-syncs on every reload of the session). It is a guide:
 * nothing ends the session when it reaches zero. Nothing is shown for a scenario with no stated length or an
 * ended session, where the server sends no time.
 */
export function SessionClock({
  secondsLeft,
  minutesTotal,
  warnings,
  onTimeout,
  onExpire,
}: {
  secondsLeft: number | null | undefined;
  minutesTotal: number | null | undefined;
  warnings?: number[];
  onTimeout?: string;
  /** Called once when the clock reaches zero (and again after the server sends a new figure that is zero). */
  onExpire?: () => void;
}) {
  const [anchor, setAnchor] = useState(() => ({ left: secondsLeft ?? null, at: Date.now() }));
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    setAnchor({ left: secondsLeft ?? null, at: Date.now() });
    setNow(Date.now());
  }, [secondsLeft]);
  const running = anchor.left !== null && anchor.left > 0;
  useEffect(() => {
    if (!running) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [running]);
  const left = anchor.left === null ? null : Math.max(0, anchor.left - Math.floor((now - anchor.at) / 1000));
  useEffect(() => {
    if (left === 0 && minutesTotal) onExpire?.();
    // once per arrival at zero, not per render of the caller
  }, [left === 0, minutesTotal]);
  if (left === null || !minutesTotal) return null;
  const banner = bannerFor(left, minutesTotal, warnings?.length ? warnings : WARNINGS, onTimeout);
  return (
    <div className={`clock-bar${left <= 0 ? " up" : banner ? " low" : ""}`}>
      <span className="session-clock" role="timer" aria-label="Time left">
        <span className="muted">Time left</span> <b>{clock(left)}</b>
      </span>
      {banner && (
        <p className="time-banner" role="status">
          {banner}
        </p>
      )}
    </div>
  );
}
