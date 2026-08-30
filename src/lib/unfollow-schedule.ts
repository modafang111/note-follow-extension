import { notifyPopup } from "./notify";
import { formatDateTime, parseStartAtMs } from "./schedule-time";
import {
  getUnfollowScheduleSettings,
  setUnfollowScheduleSettings,
} from "./storage";
import {
  appendUnfollowInfo,
  isFollowRunning,
  isUnfollowRunning,
  startUnfollowJob,
} from "./unfollow-job";
import {
  nextUnfollowAlarmWhen,
  UNFOLLOW_REPEAT_MINUTES,
} from "./unfollow-schedule-time";
import type {
  UnfollowJobResult,
  UnfollowScheduleSettings,
} from "../types";

export const UNFOLLOW_SCHEDULE_ALARM = "note-unfollow-scheduled";

export async function runScheduledUnfollow(
  trigger: "alarm" | "manual",
): Promise<UnfollowJobResult> {
  if (trigger === "alarm") {
    const settings = await getUnfollowScheduleSettings();
    if (settings.repeat === "once") {
      await setUnfollowScheduleSettings({ ...settings, enabled: false });
      await chrome.alarms.clear(UNFOLLOW_SCHEDULE_ALARM);
    }
  }

  if (await isFollowRunning()) {
    await appendUnfollowInfo(
      "フォロー返しの実行中のため、定時のフォロー解除を見送りました。",
    );
    return {
      trigger,
      found: 0,
      started: false,
      message: "フォロー返しの実行中のため、定時のフォロー解除を見送りました。",
    };
  }

  if (await isUnfollowRunning()) {
    await appendUnfollowInfo("フォロー解除の実行中のため、定時の開始はスキップしました。");
    return {
      trigger,
      found: 0,
      started: false,
      message: "フォロー解除の実行中のため、定時の開始はスキップしました。",
    };
  }

  try {
    const job = await startUnfollowJob();
    return {
      trigger,
      found: job.total,
      started: job.status === "running" || job.processed > 0,
      message: `定時のフォロー解除を開始しました（対象 ${job.total} 人）。`,
    };
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    await appendUnfollowInfo(`定時のフォロー解除: ${text}`);
    throw error;
  }
}

export async function applyUnfollowSchedule(
  settings: UnfollowScheduleSettings,
): Promise<void> {
  if (settings.enabled) {
    const startMs = parseStartAtMs(settings.startAt);
    if (startMs == null) {
      throw new Error("自動解除の開始日時を入力してください");
    }
    if (settings.repeat === "once" && startMs <= Date.now()) {
      throw new Error(
        "1回だけのときは、未来の日時を入力してください。今すぐ確認するなら解除のテスト実行を押してください。",
      );
    }
  }

  await setUnfollowScheduleSettings(settings);
  await createUnfollowScheduleAlarm(settings);
}

async function createUnfollowScheduleAlarm(
  settings: UnfollowScheduleSettings,
): Promise<void> {
  await chrome.alarms.clear(UNFOLLOW_SCHEDULE_ALARM);
  if (!settings.enabled) return;

  const startMs = parseStartAtMs(settings.startAt);
  if (startMs == null) return;
  const when = nextUnfollowAlarmWhen(startMs, Date.now(), settings.repeat);
  if (when == null) return;

  if (settings.repeat === "once") {
    await chrome.alarms.create(UNFOLLOW_SCHEDULE_ALARM, { when });
    return;
  }
  await chrome.alarms.create(UNFOLLOW_SCHEDULE_ALARM, {
    when,
    periodInMinutes: UNFOLLOW_REPEAT_MINUTES[settings.repeat],
  });
}

export async function restoreUnfollowScheduleAlarm(): Promise<void> {
  await createUnfollowScheduleAlarm(await getUnfollowScheduleSettings());
}

export async function getUnfollowScheduleStatus(): Promise<{
  settings: UnfollowScheduleSettings;
  nextLabel: string;
}> {
  const settings = await getUnfollowScheduleSettings();
  const alarm = await chrome.alarms.get(UNFOLLOW_SCHEDULE_ALARM);
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

export async function notifyUnfollowScheduleFailure(text: string): Promise<void> {
  await notifyPopup("定時のフォロー解除が失敗しました", text);
}
