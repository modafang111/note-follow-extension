import type { RuntimeResponse } from "../types";
import {
  getThanksQueue,
  getThanksSettings,
  setPendingThanksFill,
  setThanksQueue,
} from "./storage";
import { formatThanksMessage, shiftThanks } from "./thanks";

export async function getThanksState(): Promise<{
  queue: Awaited<ReturnType<typeof getThanksQueue>>;
  preview: string;
}> {
  const queue = await getThanksQueue();
  const settings = await getThanksSettings();
  const preview = queue[0]
    ? formatThanksMessage(settings.template, queue[0])
    : "";
  return { queue, preview };
}

export async function skipNextThanks(): Promise<RuntimeResponse> {
  const { next, rest } = shiftThanks(await getThanksQueue());
  await setThanksQueue(rest);
  const state = await getThanksState();
  return {
    ok: true,
    thanksQueue: state.queue,
    thanksPreview: state.preview,
    error: next ? undefined : "お礼待ちの相手はいません",
  };
}

export async function openNextThanks(
  options: { active?: boolean } = {},
): Promise<RuntimeResponse> {
  const settings = await getThanksSettings();
  if (!settings.enabled) {
    return { ok: false, error: "お礼メッセージはオプションでオフになっています" };
  }

  const { next, rest } = shiftThanks(await getThanksQueue());
  if (!next) {
    return { ok: false, error: "お礼待ちの相手はいません", thanksQueue: [] };
  }

  const body = formatThanksMessage(settings.template, next);
  await setPendingThanksFill({ urlname: next.urlname, body });
  await setThanksQueue(rest);

  const tab = await chrome.tabs.create({
    url: `https://note.com/${encodeURIComponent(next.urlname)}`,
    active: options.active ?? true,
  });

  const state = await getThanksState();
  return {
    ok: true,
    thanksQueue: state.queue,
    thanksPreview: state.preview,
    thanksOpenedBody: body,
    thanksTabId: tab.id,
  };
}
