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
import {
  formatDateTime,
  formatTestPreview,
  nextAlarmWhen,
  parseStartAtMs,
  REPEAT_MINUTES,
} from "./schedule-time";
import { mergeUrlnameText, parseUrlnames } from "./urlnames";
import { notifyPopup } from "./notify";
import type {
  Follower,
  ScheduleSettings,
  ScheduledJobResult,
  ScheduledJobTrigger,
} from "../types";

export const SCHEDULE_ALARM = "note-follow-scheduled";
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

function orderFollowersOldestFirst(followers: Follower[]): Follower[] {
  const newestFirst = followers.map((follower) => follower.urlname);
  const oldestFirst = new Set(orderFollowerUrlnamesOldestFirst(newestFirst));
  return [...oldestFirst].map((urlname) => {
    const found = followers.find((follower) => follower.urlname === urlname);
    return found ?? { urlname, isFollowing: false };
  });
}

async function collectFollowBackTargets(): Promise<string[]> {
  const me = await fetchCurrentUser();
  const followers = await collectFollowers(me.urlname);
  const completed = await getCompletedUrlnames();
  return filterFollowerUrlnames(orderFollowersOldestFirst(followers), completed);
}

export async function runTestFollowBack(): Promise<ScheduledJobResult> {
  const importedNames = await collectFollowBackTargets();
  const message = formatTestPreview(importedNames);
  await appendJobInfo(
    `テスト実行: 対象 ${importedNames.length} 人。実際のフォローはしていません。`,
  );
  for (const urlname of importedNames.slice(0, 15)) {
    await appendJobInfo(`テスト対象: ${urlname}`);
  }
  if (importedNames.length > 15) {
    await appendJobInfo(`テスト対象: ほか ${importedNames.length - 15} 人`);
  }
  await notifyPopup(
    "テスト実行が終わりました",
    `対象 ${importedNames.length} 人。実際のフォローはしていません。`,
  );
  return {
    trigger: "test",
    imported: importedNames.length,
    started: false,
    message,
  };
}

export async function runScheduledFollowBack(
  trigger: ScheduledJobTrigger,
): Promise<ScheduledJobResult> {
  if (trigger === "alarm") {
    const settings = await getScheduleSettings();
    if (settings.repeat === "once") {
      await setScheduleSettings({ ...settings, enabled: false });
      await chrome.alarms.clear(SCHEDULE_ALARM);
    }
  }

  const importedNames = await collectFollowBackTargets();
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

  const completed = await getCompletedUrlnames();
  const completedSet = new Set(completed.map((name) => name.toLowerCase()));
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

export async function applySchedule(settings: ScheduleSettings): Promise<void> {
  if (settings.enabled) {
    const startMs = parseStartAtMs(settings.startAt);
    if (startMs == null) {
      throw new Error("自動フォローの開始日時を入力してください");
    }
    if (settings.repeat === "once" && startMs <= Date.now()) {
      throw new Error(
        "1回だけのときは、未来の日時を入力してください。今すぐ確認するならテスト実行を押してください。",
      );
    }
  }

  await setScheduleSettings(settings);
  await createScheduleAlarm(settings);
}

async function createScheduleAlarm(settings: ScheduleSettings): Promise<void> {
  await chrome.alarms.clear(SCHEDULE_ALARM);
  if (!settings.enabled) return;

  const startMs = parseStartAtMs(settings.startAt);
  if (startMs == null) return;
  const when = nextAlarmWhen(startMs, Date.now(), settings.repeat);
  if (when == null) return;

  if (settings.repeat === "once") {
    await chrome.alarms.create(SCHEDULE_ALARM, { when });
    return;
  }
  await chrome.alarms.create(SCHEDULE_ALARM, {
    when,
    periodInMinutes: REPEAT_MINUTES[settings.repeat],
  });
}

export async function restoreScheduleAlarm(): Promise<void> {
  await createScheduleAlarm(await getScheduleSettings());
}

export async function getScheduleStatus(): Promise<{
  settings: ScheduleSettings;
  nextLabel: string;
}> {
  const settings = await getScheduleSettings();
  const alarm = await chrome.alarms.get(SCHEDULE_ALARM);
  let nextLabel = "未設定";
  if (!settings.enabled) {
    nextLabel = "オフ";
  } else if (alarm?.scheduledTime) {
    nextLabel = formatDateTime(alarm.scheduledTime);
  } else if (settings.startAt) {
    nextLabel = "開始日時を保存し直してください";
  }
  return { settings, nextLabel };
}
