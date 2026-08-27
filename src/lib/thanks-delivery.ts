import {
  getJob,
  getThanksQueue,
  getThanksSettings,
  setJob,
  setThanksQueue,
} from "./storage";
import { enqueueThanks } from "./thanks";
import { openNextThanks } from "./thanks-actions";

const THANKS_WAIT_MS = 25000;

type FillResult = { sent: boolean; error?: string };

const waiters = new Map<number, (result: FillResult) => void>();
let pumping = false;

export function resolveThanksFill(
  tabId: number | undefined,
  result: FillResult,
): void {
  if (tabId == null) return;
  const waiter = waiters.get(tabId);
  if (!waiter) return;
  waiters.delete(tabId);
  waiter(result);
}

function waitForThanksFill(tabId: number): Promise<FillResult> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      waiters.delete(tabId);
      resolve({ sent: false, error: "timeout" });
    }, THANKS_WAIT_MS);
    waiters.set(tabId, (result) => {
      clearTimeout(timer);
      resolve(result);
    });
  });
}

async function logThanks(message: string): Promise<void> {
  const job = await getJob();
  job.logs = [
    { urlname: "", status: "info", message, at: Date.now() },
    ...job.logs,
  ].slice(0, 80);
  await setJob(job);
}

async function closeTab(tabId?: number): Promise<void> {
  if (tabId == null) return;
  try {
    await chrome.tabs.remove(tabId);
  } catch {
    // 既に閉じられていても続行
  }
}

async function deliverNext(): Promise<boolean> {
  const queue = await getThanksQueue();
  const next = queue[0];
  if (!next) return false;

  const opened = await openNextThanks({ active: false });
  const tabId = opened.thanksTabId;
  if (!opened.ok || tabId == null) {
    await logThanks(opened.error ?? "お礼メッセージ画面を開けませんでした");
    return false;
  }

  const result = await waitForThanksFill(tabId);
  await closeTab(tabId);
  if (result.sent) {
    await logThanks(`${next.nickname} へお礼メッセージを送信しました`);
    return true;
  }

  await setThanksQueue(
    enqueueThanks(await getThanksQueue(), {
      urlname: next.urlname,
      nickname: next.nickname,
    }),
  );
  await logThanks(
    result.error === "timeout"
      ? `${next.nickname} へのお礼送信が時間内に終わりませんでした。ポップアップから送り直してください。`
      : `${next.nickname} へお礼文は入れましたが、送信ボタンを押せませんでした。ポップアップから確認してください。`,
  );
  return false;
}

export async function pumpThanksDelivery(): Promise<void> {
  if (pumping) return;
  pumping = true;
  try {
    while ((await getThanksQueue()).length > 0) {
      const progressed = await deliverNext();
      if (!progressed) break;
    }
  } finally {
    pumping = false;
  }
}

export async function queueAndDeliverThanks(item: {
  urlname: string;
  nickname: string;
}): Promise<void> {
  const settings = await getThanksSettings();
  if (!settings.enabled) return;
  const queue = await getThanksQueue();
  await setThanksQueue(enqueueThanks(queue, item));
  void pumpThanksDelivery();
}

export async function resumeThanksDelivery(): Promise<void> {
  if ((await getThanksQueue()).length === 0) return;
  void pumpThanksDelivery();
}
