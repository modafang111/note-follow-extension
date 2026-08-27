import type { ThanksItem, ThanksSettings } from "../types";

export const DEFAULT_THANKS_TEMPLATE =
  "{nickname}さん\nフォローありがとうございます。フォロー返ししました。これからよろしくお願いします。";

export const DEFAULT_THANKS_SETTINGS: ThanksSettings = {
  enabled: true,
  template: DEFAULT_THANKS_TEMPLATE,
};

export function formatThanksMessage(
  template: string,
  target: { urlname: string; nickname?: string },
): string {
  const nickname = (target.nickname ?? "").trim() || target.urlname;
  return template
    .replaceAll("{nickname}", nickname)
    .replaceAll("{urlname}", target.urlname)
    .trim();
}

export function enqueueThanks(
  queue: ThanksItem[],
  item: Omit<ThanksItem, "queuedAt">,
  now = Date.now(),
): ThanksItem[] {
  if (queue.some((existing) => existing.urlname.toLowerCase() === item.urlname.toLowerCase())) {
    return queue;
  }
  return [...queue, { ...item, queuedAt: now }];
}

export function isThanksSendLabel(label: string): boolean {
  const text = label.replace(/\s+/g, " ").trim();
  return text === "送信" || text === "送る" || text === "Send";
}

export function shiftThanks(queue: ThanksItem[]): {
  next: ThanksItem | undefined;
  rest: ThanksItem[];
} {
  const [next, ...rest] = queue;
  return { next, rest };
}
