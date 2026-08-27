import { describe, expect, it } from "vitest";
import { mergeUrlnameText } from "./urlnames";
import type { ScheduledJobResult } from "../types";

describe("ScheduledJobResult shape", () => {
  it("carries import and start flags", () => {
    const result: ScheduledJobResult = {
      trigger: "manual",
      imported: 2,
      started: true,
      message: "ok",
    };
    expect(result.imported).toBe(2);
    expect(mergeUrlnameText("a\n", ["b"])).toContain("b");
  });
});
