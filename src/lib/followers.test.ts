import { describe, expect, it } from "vitest";
import { filterFollowerUrlnames, orderFollowerUrlnamesOldestFirst } from "./followers";

describe("filterFollowerUrlnames", () => {
  it("drops already-following, completed, and duplicates", () => {
    const names = filterFollowerUrlnames(
      [
        { urlname: "new_user", isFollowing: false },
        { urlname: "already", isFollowing: true },
        { urlname: "done_user", isFollowing: false },
        { urlname: "new_user", isFollowing: false },
      ],
      ["done_user"],
    );
    expect(names).toEqual(["new_user"]);
  });
});

describe("orderFollowerUrlnamesOldestFirst", () => {
  it("reverses newest-first API order", () => {
    expect(orderFollowerUrlnamesOldestFirst(["c", "b", "a"])).toEqual([
      "a",
      "b",
      "c",
    ]);
  });
});
