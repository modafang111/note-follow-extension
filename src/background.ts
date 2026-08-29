import { appendJobInfo, FOLLOW_ALARM, handleMessage, processNext, resumeIfNeeded } from "./lib/job";
import {
  applySchedule,
  getScheduleStatus,
  restoreScheduleAlarm,
  runScheduledFollowBack,
  runTestFollowBack,
  SCHEDULE_ALARM,
} from "./lib/schedule";
import { resolveThanksFill, resumeThanksDelivery } from "./lib/thanks-delivery";
import { notifyPopup } from "./lib/notify";
import { getJob, getUnfollowJob } from "./lib/storage";
import {
  isUnfollowRunning,
  processUnfollowNext,
  resumeUnfollowIfNeeded,
  runTestUnfollow,
  startUnfollowJob,
  stopUnfollowJob,
  UNFOLLOW_ALARM,
} from "./lib/unfollow-job";
import type { RuntimeMessage, RuntimeResponse } from "./types";

async function scheduleResponse(): Promise<RuntimeResponse> {
  const { settings, nextLabel } = await getScheduleStatus();
  return {
    ok: true,
    schedule: settings,
    scheduleEnabled: settings.enabled,
    scheduleNextLabel: nextLabel,
  };
}

async function dispatch(message: RuntimeMessage): Promise<RuntimeResponse> {
  try {
    if (message.type === "GET_UNFOLLOW") {
      return { ok: true, unfollowJob: await getUnfollowJob() };
    }
    if (message.type === "TEST_UNFOLLOW") {
      const unfollow = await runTestUnfollow();
      return { ok: true, unfollow, unfollowJob: await getUnfollowJob() };
    }
    if (message.type === "START_UNFOLLOW") {
      return { ok: true, unfollowJob: await startUnfollowJob() };
    }
    if (message.type === "STOP_UNFOLLOW") {
      return { ok: true, unfollowJob: await stopUnfollowJob() };
    }
    if (
      (message.type === "IMPORT_FOLLOWERS" ||
        message.type === "START_FOLLOW" ||
        message.type === "TEST_FOLLOW") &&
      (await isUnfollowRunning())
    ) {
      return {
        ok: false,
        error: "フォロー解除の実行中は、フォロー返しを開始できません。終わるまで待ってください。",
        job: await getJob(),
        unfollowJob: await getUnfollowJob(),
      };
    }
    if (message.type === "IMPORT_FOLLOWERS") {
      const scheduled = await runScheduledFollowBack("manual");
      return { ok: true, scheduled, job: await getJob() };
    }
    if (message.type === "TEST_FOLLOW") {
      const scheduled = await runTestFollowBack();
      return { ok: true, scheduled, job: await getJob() };
    }
    if (message.type === "GET_SCHEDULE") {
      return scheduleResponse();
    }
    if (message.type === "SET_SCHEDULE") {
      await applySchedule(message.settings);
      return scheduleResponse();
    }
    return handleMessage(message);
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : String(error),
      job: await getJob(),
      unfollowJob: await getUnfollowJob(),
    };
  }
}

chrome.runtime.onMessage.addListener((message: RuntimeMessage, sender, sendResponse) => {
  if (message.type === "THANKS_FILL_RESULT") {
    resolveThanksFill(sender.tab?.id, {
      sent: message.sent,
      error: message.error,
    });
    sendResponse({ ok: true });
    return false;
  }
  void dispatch(message).then(sendResponse);
  return true;
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === FOLLOW_ALARM) {
    void processNext();
    return;
  }
  if (alarm.name === UNFOLLOW_ALARM) {
    void processUnfollowNext();
    return;
  }
  if (alarm.name === SCHEDULE_ALARM) {
    void (async () => {
      if (await isUnfollowRunning()) {
        await appendJobInfo(
          "フォロー解除の実行中のため、定時のフォロー返しを見送りました。",
        );
        await notifyPopup(
          "定時のフォロー返しを見送りました",
          "フォロー解除が終わるまで待ちます。",
        );
        return;
      }
      await runScheduledFollowBack("alarm").catch(async (error) => {
        const text = error instanceof Error ? error.message : String(error);
        await appendJobInfo(`定時のフォロー返しに失敗しました: ${text}`);
        await notifyPopup("定時のフォロー返しが失敗しました", text);
      });
    })();
  }
});

chrome.runtime.onInstalled.addListener(() => {
  void resumeIfNeeded();
  void restoreScheduleAlarm();
  void resumeThanksDelivery();
  void resumeUnfollowIfNeeded();
});

chrome.runtime.onStartup.addListener(() => {
  void resumeIfNeeded();
  void restoreScheduleAlarm();
  void resumeThanksDelivery();
  void resumeUnfollowIfNeeded();
});

void resumeIfNeeded();
void restoreScheduleAlarm();
void resumeThanksDelivery();
void resumeUnfollowIfNeeded();
