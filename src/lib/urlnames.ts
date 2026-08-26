import type { FollowDecision } from "../types";

const URLNAME_RE = /^[a-zA-Z0-9][a-zA-Z0-9_.-]*$/;

export function parseUrlnames(text: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;

    const urlname = normalizeUrlname(line);
    if (!urlname) continue;

    const key = urlname.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(urlname);
  }

  return result;
}

export function normalizeUrlname(input: string): string | null {
  let value = input.trim();
  if (!value) return null;

  value = value.replace(/^@/, "");

  try {
    if (/^https?:\/\//i.test(value)) {
      const url = new URL(value);
      if (!/(^|\.)note\.com$/i.test(url.hostname)) return null;
      value = url.pathname.replace(/^\/+/, "").split("/")[0] ?? "";
    } else if (/^(www\.)?note\.com\//i.test(value)) {
      value = value.replace(/^(www\.)?note\.com\//i, "").split("/")[0] ?? "";
    }
    value = decodeURIComponent(value).replace(/\/+$/, "");
  } catch {
    return null;
  }
  if (!value || !URLNAME_RE.test(value)) return null;
  return value;
}

export function randomDelayMs(
  min = 3000,
  max = 5000,
  random: () => number = Math.random,
): number {
  if (max < min) {
    throw new Error("max must be >= min");
  }
  return Math.floor(min + random() * (max - min + 1));
}

export function decideFollowAction(creator: {
  isFollowing: boolean;
  isMyself: boolean;
}): FollowDecision {
  if (creator.isMyself) return "skip-myself";
  if (creator.isFollowing) return "skip-following";
  return "follow";
}
