import { describe, expect, it } from "vitest";
import {
  formatTestPreview,
  nextAlarmWhen,
  parseStartAtMs,
  REPEAT_MINUTES,
} from "./schedule-time";

describe("parseStartAtMs", () => {
  it("parses datetime-local values", () => {
    const ms = parseStartAtMs("2026-08-27T10:00");
    expect(ms).not.toBeNull();
    expect(new Date(ms as number).getHours()).toBe(10);
  });

  it("rejects empty input", () => {
    expect(parseStartAtMs("")).toBeNull();
    expect(parseStartAtMs("   ")).toBeNull();
  });
});

describe("nextAlarmWhen", () => {
  const start = Date.parse("2026-08-27T10:00:00");

  it("uses the future start time as-is", () => {
    expect(nextAlarmWhen(start, start - 60_000, "daily")).toBe(start);
  });

  it("does not resurrect a one-shot that already passed", () => {
    expect(nextAlarmWhen(start, start + 60_000, "once")).toBeNull();
  });

  it("schedules the next daily slot after the start time", () => {
    const now = start + 3 * 60 * 60 * 1000;
    expect(nextAlarmWhen(start, now, "daily")).toBe(start + 24 * 60 * 60 * 1000);
  });

  it("uses 30 minute and hourly periods", () => {
    expect(REPEAT_MINUTES["every-30m"]).toBe(30);
    expect(REPEAT_MINUTES.hourly).toBe(60);
    const now = start + 40 * 60 * 1000;
    expect(nextAlarmWhen(start, now, "every-30m")).toBe(start + 60 * 60 * 1000);
  });
});

describe("formatTestPreview", () => {
  it("says no targets without following anyone", () => {
    expect(formatTestPreview([])).toContain("実際のフォローはしていません");
    expect(formatTestPreview([])).toContain("対象はいませんでした");
  });

  it("lists urlnames and a remainder", () => {
    const names = Array.from({ length: 17 }, (_, i) => `user${i + 1}`);
    const text = formatTestPreview(names, 15);
    expect(text).toContain("対象 17 人");
    expect(text).toContain("・user1");
    expect(text).toContain("ほか 2 人");
    expect(text).not.toContain("・user16");
  });
});
