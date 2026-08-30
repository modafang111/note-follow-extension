import { describe, expect, it } from "vitest";
import {
  nextUnfollowAlarmWhen,
  UNFOLLOW_REPEAT_MINUTES,
} from "./unfollow-schedule-time";

describe("nextUnfollowAlarmWhen", () => {
  const start = Date.parse("2026-08-30T10:00:00");

  it("uses the future start time as-is", () => {
    expect(nextUnfollowAlarmWhen(start, start - 60_000, "weekly")).toBe(start);
  });

  it("does not resurrect a one-shot that already passed", () => {
    expect(nextUnfollowAlarmWhen(start, start + 60_000, "once")).toBeNull();
  });

  it("schedules the next weekly slot after the start time", () => {
    const now = start + 3 * 60 * 60 * 1000;
    expect(nextUnfollowAlarmWhen(start, now, "weekly")).toBe(
      start + 7 * 24 * 60 * 60 * 1000,
    );
  });

  it("uses a 7-day period", () => {
    expect(UNFOLLOW_REPEAT_MINUTES.weekly).toBe(7 * 24 * 60);
  });
});
