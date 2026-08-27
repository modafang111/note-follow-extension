import { appendJobInfo, FOLLOW_ALARM, handleMessage, processNext, resumeIfNeeded } from "./lib/job";
import {
  restoreScheduleAlarm,
  runScheduledFollowBack,
  SCHEDULE_ALARM,
  setScheduleEnabled,
} from "./lib/schedule";
import { getJob, getScheduleSettings } from "./lib/storage";
import type { RuntimeMessage, RuntimeResponse } from "./types";

async function dispatch(message: RuntimeMessage): Promise<RuntimeResponse> {
  try {
    if (message.type === "IMPORT_FOLLOWERS") {
      const scheduled = await runScheduledFollowBack("manual");
      return { ok: true, scheduled, job: await getJob() };
    }
    if (message.type === "GET_SCHEDULE") {
      const { enabled } = await getScheduleSettings();
      return { ok: true, scheduleEnabled: enabled };
    }
    if (message.type === "SET_SCHEDULE") {
      await setScheduleEnabled(message.enabled);
      return { ok: true, scheduleEnabled: message.enabled };
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

chrome.runtime.onMessage.addListener((message: RuntimeMessage, _sender, sendResponse) => {
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
});

chrome.runtime.onStartup.addListener(() => {
  void resumeIfNeeded();
  void restoreScheduleAlarm();
});

void resumeIfNeeded();
void restoreScheduleAlarm();
