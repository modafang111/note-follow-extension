import { formatDateTime } from "./schedule-time";
import type { JobState, UnfollowJobState } from "../types";

export async function syncJobBadge(job: JobState): Promise<void> {
  if (job.status === "running") {
    await chrome.action.setBadgeBackgroundColor({ color: "#2cb696" });
    await chrome.action.setBadgeText({ text: "実行" });
    return;
  }
  if (job.status === "completed") {
    await chrome.action.setBadgeBackgroundColor({ color: "#3558a0" });
    await chrome.action.setBadgeText({ text: "完了" });
    return;
  }
  if (job.status === "stopped") {
    await chrome.action.setBadgeBackgroundColor({ color: "#c0392b" });
    await chrome.action.setBadgeText({ text: "停止" });
    return;
  }
  await chrome.action.setBadgeText({ text: "" });
}

export async function notifyPopup(title: string, message: string): Promise<void> {
  const when = formatDateTime(Date.now());
  try {
    await chrome.notifications.create(`note-follow-${Date.now()}`, {
      type: "basic",
      iconUrl: chrome.runtime.getURL("icons/icon128.png"),
      title,
      message: `${when}\n${message}`,
      priority: 2,
    });
  } catch {
    // 通知が許可されていない環境でもフォロー処理は続ける
  }
}

export async function notifyJobFinished(job: JobState): Promise<void> {
  await syncJobBadge(job);
  const counts = `フォロー ${job.followed} / スキップ ${job.skipped} / 失敗 ${job.failed}`;
  if (job.status === "completed") {
    await notifyPopup("フォロー返しが終わりました", counts);
    return;
  }
  if (job.status === "stopped") {
    await notifyPopup(
      job.error ? "フォロー返しが止まりました" : "フォロー返しを停止しました",
      job.error ? job.error : counts,
    );
  }
}

export async function syncUnfollowBadge(job: UnfollowJobState): Promise<void> {
  if (job.status === "running") {
    await chrome.action.setBadgeBackgroundColor({ color: "#c0392b" });
    await chrome.action.setBadgeText({ text: "解除" });
    return;
  }
  if (job.status === "completed") {
    await chrome.action.setBadgeBackgroundColor({ color: "#3558a0" });
    await chrome.action.setBadgeText({ text: "完了" });
    return;
  }
  if (job.status === "stopped") {
    await chrome.action.setBadgeBackgroundColor({ color: "#c0392b" });
    await chrome.action.setBadgeText({ text: "停止" });
    return;
  }
  // idle ではフォロー返しのバッジを消さない
}

export async function notifyUnfollowFinished(job: UnfollowJobState): Promise<void> {
  await syncUnfollowBadge(job);
  const counts = `解除 ${job.unfollowed} / スキップ ${job.skipped} / 失敗 ${job.failed}`;
  if (job.status === "completed") {
    await notifyPopup("フォロー解除が終わりました", counts);
    return;
  }
  if (job.status === "stopped") {
    await notifyPopup(
      job.error ? "フォロー解除が止まりました" : "フォロー解除を停止しました",
      job.error ? job.error : counts,
    );
  }
}
