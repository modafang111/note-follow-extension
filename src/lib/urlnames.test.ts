import { describe, expect, it } from "vitest";
import { decideFollowAction, normalizeUrlname, parseUrlnames, randomDelayMs } from "./urlnames";

describe("normalizeUrlname", () => {
  it("accepts a plain urlname", () => {
    expect(normalizeUrlname("fuji1080")).toBe("fuji1080");
  });

  it("strips @ and note.com URLs", () => {
    expect(normalizeUrlname("@fuji1080")).toBe("fuji1080");
    expect(normalizeUrlname("https://note.com/fuji1080")).toBe("fuji1080");
    expect(normalizeUrlname("https://note.com/fuji1080/n/n123")).toBe("fuji1080");
    expect(normalizeUrlname("note.com/fuji1080")).toBe("fuji1080");
  });

  it("rejects unrelated hosts", () => {
    expect(normalizeUrlname("https://example.com/fuji1080")).toBeNull();
  });
});

describe("parseUrlnames", () => {
  it("parses one urlname per line, skips comments and duplicates", () => {
    const text = `
      fuji1080
      # comment
      https://note.com/other_user
      fuji1080
      @other_user
    `;
    expect(parseUrlnames(text)).toEqual(["fuji1080", "other_user"]);
  });
});

describe("randomDelayMs", () => {
  it("stays within 3–5 seconds", () => {
    expect(randomDelayMs(3000, 5000, () => 0)).toBe(3000);
    expect(randomDelayMs(3000, 5000, () => 0.999999999)).toBe(5000);
    for (const r of [0.1, 0.5, 0.8]) {
      const ms = randomDelayMs(3000, 5000, () => r);
      expect(ms).toBeGreaterThanOrEqual(3000);
      expect(ms).toBeLessThanOrEqual(5000);
    }
  });
});

describe("decideFollowAction", () => {
  it("skips already followed and self", () => {
    expect(decideFollowAction({ isFollowing: true, isMyself: false })).toBe(
      "skip-following",
    );
    expect(decideFollowAction({ isFollowing: false, isMyself: true })).toBe(
      "skip-myself",
    );
    expect(decideFollowAction({ isFollowing: false, isMyself: false })).toBe(
      "follow",
    );
  });
});
