import type { Follower } from "../types";

export function filterFollowerUrlnames(
  followers: Follower[],
  completed: Iterable<string> = [],
): string[] {
  const done = new Set(
    [...completed].map((name) => name.trim().toLowerCase()).filter(Boolean),
  );
  const seen = new Set<string>();
  const result: string[] = [];

  for (const follower of followers) {
    const urlname = follower.urlname?.trim();
    if (!urlname) continue;
    const key = urlname.toLowerCase();
    if (seen.has(key) || done.has(key)) continue;
    if (follower.isFollowing) continue;
    seen.add(key);
    result.push(urlname);
  }

  return result;
}

export function orderFollowerUrlnamesOldestFirst(newestFirst: string[]): string[] {
  return [...newestFirst].reverse();
}
