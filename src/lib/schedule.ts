import { appendJobInfo, appendToRunningQueue, startFollowJob } from "./job";
import {
  fetchCurrentUser,
  fetchFollowersPage,
} from "./note-api";
import { filterFollowerUrlnames, orderFollowerUrlnamesOldestFirst } from "./followers";
import {
  getCompletedUrlnames,
  getJob,
  getScheduleSettings,
  getUrlnamesText,
  setScheduleSettings,
  setUrlnamesText,
} from "./storage";
import { mergeUrlnameText, parseUrlnames } from "./urlnames";
import type { Follower, ScheduledJobResult, ScheduledJobTrigger } from "../types";

export const SCHEDULE_ALARM = "note-follow-scheduled";
export const SCHEDULE_PERIOD_MINUTES = 30;
const MAX_FOLLOWER_PAGES = 80;

async function collectFollowers(urlname: string): Promise<Follower[]> {
  const all: Follower[] = [];
  for (let page = 1; page <= MAX_FOLLOWER_PAGES; page += 1) {
    const data = await fetchFollowersPage(urlname, page);
    all.push(...data.follows);
    if (data.isLastPage || data.follows.length === 0) break;
  }
  return all;
}

export async function runScheduledFollowBack(
  trigger: ScheduledJobTrigger,
): Promise<ScheduledJobResult> {
  const me = await fetchCurrentUser();
  const followers = await collectFollowers(me.urlname);
  const newestFirst = followers.map((follower) => follower.urlname);
  const oldestFirst = new Set(orderFollowerUrlnamesOldestFirst(newestFirst));
  const orderedFollowers = [...oldestFirst].map((urlname) => {
    const found = followers.find((follower) => follower.urlname === urlname);
    return found ?? { urlname, isFollowing: false };
  });

  const completed = await getCompletedUrlnames();
  const completedSet = new Set(completed.map((name) => name.toLowerCase()));
  const importedNames = filterFollowerUrlnames(orderedFollowers, completed);
  const existing = await getUrlnamesText();
  const existingNames = new Set(
    parseUrlnames(existing).map((name) => name.toLowerCase()),
  );
  const merged = mergeUrlnameText(existing, importedNames);
  const added = importedNames.filter(
    (name) => !existingNames.has(name.toLowerCase()),
  );
  if (merged !== existing) {
    await setUrlnamesText(merged);
  }

  const pending = parseUrlnames(merged).filter(
    (name) => !completedSet.has(name.toLowerCase()),
  );

  const job = await getJob();
  if (job.status === "running") {
    const queued = await appendToRunningQueue(importedNames);
    if (queued === 0) {
      await appendJobInfo(
        `フォロワーを確認しました（追加 ${added.length} 人、実行中のため開始はスキップ）`,
      );
    }
    return {
      trigger,
      imported: added.length,
      started: false,
      message:
        queued > 0
          ? `取り込み ${added.length} 人。実行中のキューに追加しました。`
          : `取り込み ${added.length} 人。フォロー実行中のため開始はスキップしました。`,
    };
  }

  if (pending.length === 0) {
    await appendJobInfo("新しくフォロー返しする相手はいませんでした。");
    return {
      trigger,
      imported: 0,
      started: false,
      message: "新しくフォロー返しする相手はいませんでした。",
    };
  }

  await appendJobInfo(`フォロワーから ${added.length} 人を追加してフォローを開始します`);
  try {
    await startFollowJob();
    return {
      trigger,
      imported: added.length,
      started: true,
      message: `取り込み ${added.length} 人。フォローを開始しました。`,
    };
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    await appendJobInfo(text);
    throw error;
  }
}

export async function setScheduleEnabled(enabled: boolean): Promise<void> {
  const previous = await getScheduleSettings();
  await setScheduleSettings({ enabled });
  await chrome.alarms.clear(SCHEDULE_ALARM);
  if (!enabled) return;

  await chrome.alarms.create(SCHEDULE_ALARM, {
    periodInMinutes: SCHEDULE_PERIOD_MINUTES,
    delayInMinutes: SCHEDULE_PERIOD_MINUTES,
  });
  if (previous.enabled) return;

  try {
    await runScheduledFollowBack("manual");
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    await appendJobInfo(`自動フォロー返しの開始に失敗しました: ${text}`);
  }
}

export async function restoreScheduleAlarm(): Promise<void> {
  const { enabled } = await getScheduleSettings();
  if (!enabled) {
    await chrome.alarms.clear(SCHEDULE_ALARM);
    return;
  }
  const existing = await chrome.alarms.get(SCHEDULE_ALARM);
  if (!existing) {
    await chrome.alarms.create(SCHEDULE_ALARM, {
      periodInMinutes: SCHEDULE_PERIOD_MINUTES,
      delayInMinutes: SCHEDULE_PERIOD_MINUTES,
    });
  }
}
