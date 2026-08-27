import type { ScheduleRepeat } from "../types";

export const REPEAT_MINUTES: Record<Exclude<ScheduleRepeat, "once">, number> = {
  "every-30m": 30,
  hourly: 60,
  daily: 1440,
};

export function parseStartAtMs(startAt: string): number | null {
  const value = startAt.trim();
  if (!value) return null;
  const normalized = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)
    ? `${value}:00`
    : value;
  const ms = new Date(normalized).getTime();
  return Number.isFinite(ms) ? ms : null;
}

export function nextAlarmWhen(
  startAtMs: number,
  nowMs: number,
  repeat: ScheduleRepeat,
): number | null {
  if (startAtMs > nowMs) return startAtMs;
  if (repeat === "once") return null;
  const period = REPEAT_MINUTES[repeat] * 60 * 1000;
  const elapsed = nowMs - startAtMs;
  const steps = Math.floor(elapsed / period) + 1;
  return startAtMs + steps * period;
}

export function formatDateTime(ms: number): string {
  const date = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function formatTestPreview(urlnames: string[], limit = 15): string {
  if (urlnames.length === 0) {
    return "テスト実行: 対象はいませんでした。実際のフォローはしていません。";
  }
  const shown = urlnames.slice(0, limit);
  const rest = urlnames.length - shown.length;
  const lines = shown.map((name) => `・${name}`).join("\n");
  const extra = rest > 0 ? `\nほか ${rest} 人` : "";
  return `テスト実行: 対象 ${urlnames.length} 人。実際のフォローはしていません。\n${lines}${extra}`;
}
