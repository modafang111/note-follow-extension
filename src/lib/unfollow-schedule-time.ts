import type { UnfollowScheduleRepeat } from "../types";

export const UNFOLLOW_REPEAT_MINUTES: Record<
  Exclude<UnfollowScheduleRepeat, "once">,
  number
> = {
  weekly: 7 * 24 * 60,
};

export function nextUnfollowAlarmWhen(
  startAtMs: number,
  nowMs: number,
  repeat: UnfollowScheduleRepeat,
): number | null {
  if (startAtMs > nowMs) return startAtMs;
  if (repeat === "once") return null;
  const period = UNFOLLOW_REPEAT_MINUTES[repeat] * 60 * 1000;
  const elapsed = nowMs - startAtMs;
  const steps = Math.floor(elapsed / period) + 1;
  return startAtMs + steps * period;
}
