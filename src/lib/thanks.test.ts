import { describe, expect, it } from "vitest";
import { enqueueThanks, formatThanksMessage, isThanksSendLabel, shiftThanks } from "./thanks";

describe("formatThanksMessage", () => {
  it("replaces nickname and urlname", () => {
    expect(
      formatThanksMessage("{nickname}さん (@{urlname}) ありがとう", {
        urlname: "fuji1080",
        nickname: "ブオナローティ",
      }),
    ).toBe("ブオナローティさん (@fuji1080) ありがとう");
  });

  it("falls back to urlname when nickname is empty", () => {
    expect(
      formatThanksMessage("{nickname}さん、ありがとう", { urlname: "fuji1080" }),
    ).toBe("fuji1080さん、ありがとう");
  });
});

describe("isThanksSendLabel", () => {
  it("accepts note.com send buttons only", () => {
    expect(isThanksSendLabel("送信")).toBe(true);
    expect(isThanksSendLabel("送る")).toBe(true);
    expect(isThanksSendLabel("Send")).toBe(true);
    expect(isThanksSendLabel("送信取り消し")).toBe(false);
    expect(isThanksSendLabel("メッセージ")).toBe(false);
  });
});

describe("thanks queue", () => {
  it("dedupes urlnames and shifts in order", () => {
    let queue = enqueueThanks([], { urlname: "a", nickname: "A" }, 1);
    queue = enqueueThanks(queue, { urlname: "a", nickname: "A" }, 2);
    queue = enqueueThanks(queue, { urlname: "b", nickname: "B" }, 3);
    expect(queue.map((item) => item.urlname)).toEqual(["a", "b"]);

    const first = shiftThanks(queue);
    expect(first.next?.urlname).toBe("a");
    expect(first.rest.map((item) => item.urlname)).toEqual(["b"]);
  });
});
