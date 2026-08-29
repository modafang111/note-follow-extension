import type { Following, UnfollowReason, UnfollowTarget } from "../types";

export function unfollowReason(person: Following): UnfollowReason | null {
  if (person.withdrawal) return "withdrawn";
  if (!person.isFollowed) return "not-followed";
  return null;
}

export function unfollowReasonLabel(reason: UnfollowReason): string {
  if (reason === "withdrawn") return "退会しているため";
  return "フォローされていないため";
}

export function filterUnfollowTargets(
  followings: Following[],
  completed: Iterable<string> = [],
): UnfollowTarget[] {
  const done = new Set(
    [...completed].map((name) => name.trim().toLowerCase()).filter(Boolean),
  );
  const seen = new Set<string>();
  const result: UnfollowTarget[] = [];

  for (const person of followings) {
    const urlname = person.urlname?.trim();
    const key = person.key?.trim();
    if (!urlname || !key) continue;
    const id = urlname.toLowerCase();
    if (seen.has(id) || done.has(id)) continue;
    const reason = unfollowReason(person);
    if (!reason) continue;
    seen.add(id);
    result.push({
      urlname,
      key,
      nickname: person.nickname,
      reason,
    });
  }

  return result;
}

export function orderUnfollowTargetsOldestFirst(
  newestFirst: UnfollowTarget[],
): UnfollowTarget[] {
  return [...newestFirst].reverse();
}

export function formatUnfollowTestPreview(
  targets: UnfollowTarget[],
  limit = 15,
): string {
  if (targets.length === 0) {
    return "解除のテスト実行: 対象はいませんでした。実際の解除はしていません。";
  }
  const shown = targets.slice(0, limit);
  const rest = targets.length - shown.length;
  const lines = shown
    .map((target) => `・${target.urlname}（${unfollowReasonLabel(target.reason)}）`)
    .join("\n");
  const extra = rest > 0 ? `\nほか ${rest} 人` : "";
  return `解除のテスト実行: 対象 ${targets.length} 人。実際の解除はしていません。\n${lines}${extra}`;
}
