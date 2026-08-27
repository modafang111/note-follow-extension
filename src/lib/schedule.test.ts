import { describe, expect, it } from "vitest";
import { mergeUrlnameText } from "./urlnames";
import type { ScheduledJobResult } from "../types";

describe("ScheduledJobResult shape", () => {
  it("carries import, start, and test trigger flags", () => {
    const result: ScheduledJobResult = {
      trigger: "test",
      imported: 2,
      started: false,
      message: "ok",
    };
    expect(result.trigger).toBe("test");
    expect(result.started).toBe(false);
    expect(mergeUrlnameText("a\n", ["b"])).toContain("b");
  });
});
