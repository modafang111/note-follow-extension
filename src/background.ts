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
import { getJob } from "./lib/storage";
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
  if (alarm.name === SCHEDULE_ALARM) {
    void runScheduledFollowBack("alarm").catch(async (error) => {
      const text = error instanceof Error ? error.message : String(error);
      await appendJobInfo(`定時のフォロー返しに失敗しました: ${text}`);
    });
  }
});

chrome.runtime.onInstalled.addListener(() => {
  void resumeIfNeeded();
  void restoreScheduleAlarm();
  void resumeThanksDelivery();
});

chrome.runtime.onStartup.addListener(() => {
  void resumeIfNeeded();
  void restoreScheduleAlarm();
  void resumeThanksDelivery();
});

void resumeIfNeeded();
void restoreScheduleAlarm();
void resumeThanksDelivery();
