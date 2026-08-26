import { FOLLOW_ALARM, handleMessage, processNext, resumeIfNeeded } from "./lib/job";
import type { RuntimeMessage } from "./types";

chrome.runtime.onMessage.addListener((message: RuntimeMessage, _sender, sendResponse) => {
  void handleMessage(message).then(sendResponse);
  return true;
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === FOLLOW_ALARM) {
    void processNext();
  }
});

chrome.runtime.onInstalled.addListener(() => {
  void resumeIfNeeded();
});

chrome.runtime.onStartup.addListener(() => {
  void resumeIfNeeded();
});

void resumeIfNeeded();
