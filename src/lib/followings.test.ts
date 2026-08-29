import { describe, expect, it } from "vitest";
import {
  filterUnfollowTargets,
  formatUnfollowTestPreview,
  orderUnfollowTargetsOldestFirst,
  unfollowReason,
} from "./followings";
import type { Following } from "../types";

function person(partial: Partial<Following> & Pick<Following, "urlname" | "key">): Following {
  return {
    isFollowing: true,
    isFollowed: true,
    withdrawal: false,
    ...partial,
  };
}

describe("unfollowReason", () => {
  it("prefers withdrawal over not-followed", () => {
    expect(
      unfollowReason(person({ urlname: "gone", key: "k1", withdrawal: true, isFollowed: false })),
    ).toBe("withdrawn");
  });

  it("marks people who do not follow back", () => {
    expect(
      unfollowReason(person({ urlname: "oneway", key: "k2", isFollowed: false })),
    ).toBe("not-followed");
  });

  it("keeps mutual follows", () => {
    expect(unfollowReason(person({ urlname: "mutual", key: "k3" }))).toBeNull();
  });
});

describe("filterUnfollowTargets", () => {
  it("keeps withdrawn and not-followed, skips mutual, completed, and duplicates", () => {
    const targets = filterUnfollowTargets(
      [
        person({ urlname: "gone", key: "k1", withdrawal: true }),
        person({ urlname: "oneway", key: "k2", isFollowed: false }),
        person({ urlname: "mutual", key: "k3" }),
        person({ urlname: "done_user", key: "k4", isFollowed: false }),
        person({ urlname: "gone", key: "k1", withdrawal: true }),
        person({ urlname: "nokey", key: "", isFollowed: false }),
      ],
      ["done_user"],
    );
    expect(targets.map((item) => item.urlname)).toEqual(["gone", "oneway"]);
    expect(targets[0]?.reason).toBe("withdrawn");
    expect(targets[1]?.reason).toBe("not-followed");
  });
});

describe("orderUnfollowTargetsOldestFirst", () => {
  it("reverses newest-first API order", () => {
    const ordered = orderUnfollowTargetsOldestFirst([
      { urlname: "c", key: "3", reason: "not-followed" },
      { urlname: "b", key: "2", reason: "withdrawn" },
      { urlname: "a", key: "1", reason: "not-followed" },
    ]);
    expect(ordered.map((item) => item.urlname)).toEqual(["a", "b", "c"]);
  });
});

describe("formatUnfollowTestPreview", () => {
  it("says no targets when the list is empty", () => {
    expect(formatUnfollowTestPreview([])).toContain("対象はいませんでした");
    expect(formatUnfollowTestPreview([])).toContain("実際の解除はしていません");
  });

  it("lists urlnames, reasons, and a remainder", () => {
    const targets = Array.from({ length: 17 }, (_, i) => ({
      urlname: `user${i + 1}`,
      key: `k${i + 1}`,
      reason: i % 2 === 0 ? ("withdrawn" as const) : ("not-followed" as const),
    }));
    const text = formatUnfollowTestPreview(targets, 15);
    expect(text).toContain("対象 17 人");
    expect(text).toContain("・user1（退会しているため）");
    expect(text).toContain("ほか 2 人");
    expect(text).not.toContain("・user16");
  });
});
