import {
  getThanksSettings,
  getUrlnamesText,
  setThanksSettings,
  setUrlnamesText,
} from "../lib/storage";
import { DEFAULT_THANKS_TEMPLATE } from "../lib/thanks";
import { parseUrlnames } from "../lib/urlnames";
import type {
  RuntimeMessage,
  RuntimeResponse,
  ScheduleRepeat,
  UnfollowScheduleRepeat,
} from "../types";

const textarea = document.querySelector<HTMLTextAreaElement>("#urlnames")!;
const saveBtn = document.querySelector<HTMLButtonElement>("#save-btn")!;
const testBtn = document.querySelector<HTMLButtonElement>("#test-btn")!;
const savedEl = document.querySelector<HTMLElement>("#saved")!;
const countEl = document.querySelector<HTMLElement>("#count")!;
const scheduleEnabled = document.querySelector<HTMLInputElement>("#schedule-enabled")!;
const scheduleStart = document.querySelector<HTMLInputElement>("#schedule-start")!;
const scheduleRepeat = document.querySelector<HTMLSelectElement>("#schedule-repeat")!;
const testResult = document.querySelector<HTMLElement>("#test-result")!;
const thanksEnabled = document.querySelector<HTMLInputElement>("#thanks-enabled")!;
const thanksTemplate = document.querySelector<HTMLTextAreaElement>("#thanks-template")!;
const unfollowScheduleEnabled = document.querySelector<HTMLInputElement>(
  "#unfollow-schedule-enabled",
)!;
const unfollowScheduleStart = document.querySelector<HTMLInputElement>(
  "#unfollow-schedule-start",
)!;
const unfollowScheduleRepeat = document.querySelector<HTMLSelectElement>(
  "#unfollow-schedule-repeat",
)!;
const unfollowSaveBtn = document.querySelector<HTMLButtonElement>("#unfollow-save-btn")!;
const unfollowTestBtn = document.querySelector<HTMLButtonElement>("#unfollow-test-btn")!;
const unfollowSavedEl = document.querySelector<HTMLElement>("#unfollow-saved")!;
const unfollowTestResult = document.querySelector<HTMLElement>("#unfollow-test-result")!;

function send(message: RuntimeMessage): Promise<RuntimeResponse> {
  return chrome.runtime.sendMessage(message);
}

function isScheduleRepeat(value: string): value is ScheduleRepeat {
  return (
    value === "once" ||
    value === "every-30m" ||
    value === "hourly" ||
    value === "daily"
  );
}

function readSchedule() {
  const repeat = scheduleRepeat.value;
  return {
    enabled: scheduleEnabled.checked,
    startAt: scheduleStart.value,
    repeat: isScheduleRepeat(repeat) ? repeat : "daily",
  };
}

function flash(el: HTMLElement, text: string, ok = true): void {
  el.hidden = false;
  el.textContent = text;
  el.classList.toggle("error-text", !ok);
  window.setTimeout(() => {
    el.hidden = true;
  }, ok ? 1600 : 4000);
}

function updateCount(): void {
  const n = parseUrlnames(textarea.value).length;
  countEl.textContent = `${n} 人`;
}

textarea.addEventListener("input", updateCount);

saveBtn.addEventListener("click", () => {
  void (async () => {
    await setUrlnamesText(textarea.value);
    await setThanksSettings({
      enabled: thanksEnabled.checked,
      template: thanksTemplate.value.trim() || DEFAULT_THANKS_TEMPLATE,
    });
    const scheduleRes = await send({
      type: "SET_SCHEDULE",
      settings: readSchedule(),
    });
    if (!scheduleRes.ok) {
      flash(savedEl, scheduleRes.error ?? "自動フォローの保存に失敗しました", false);
      return;
    }
    updateCount();
    flash(savedEl, "保存しました");
  })();
});

function isUnfollowScheduleRepeat(value: string): value is UnfollowScheduleRepeat {
  return value === "once" || value === "weekly";
}

function readUnfollowSchedule() {
  const repeat = unfollowScheduleRepeat.value;
  return {
    enabled: unfollowScheduleEnabled.checked,
    startAt: unfollowScheduleStart.value,
    repeat: isUnfollowScheduleRepeat(repeat) ? repeat : "weekly",
  };
}

unfollowSaveBtn.addEventListener("click", () => {
  void (async () => {
    const res = await send({
      type: "SET_UNFOLLOW_SCHEDULE",
      settings: readUnfollowSchedule(),
    });
    if (!res.ok) {
      flash(unfollowSavedEl, res.error ?? "解除の日時の保存に失敗しました", false);
      return;
    }
    flash(unfollowSavedEl, "保存しました");
  })();
});

unfollowTestBtn.addEventListener("click", () => {
  void (async () => {
    unfollowTestBtn.disabled = true;
    unfollowTestResult.hidden = true;
    const res = await send({ type: "TEST_UNFOLLOW" });
    unfollowTestResult.hidden = false;
    unfollowTestResult.textContent = res.ok
      ? (res.unfollow?.message ?? "解除のテスト実行が完了しました。")
      : (res.error ?? "解除のテスト実行に失敗しました");
    unfollowTestBtn.disabled = false;
  })();
});

testBtn.addEventListener("click", () => {
  void (async () => {
    testBtn.disabled = true;
    testResult.hidden = true;
    const res = await send({ type: "TEST_FOLLOW" });
    testResult.hidden = false;
    testResult.textContent = res.ok
      ? (res.scheduled?.message ?? "テスト実行が完了しました。")
      : (res.error ?? "テスト実行に失敗しました");
    testBtn.disabled = false;
  })();
});

void (async () => {
  textarea.value = await getUrlnamesText();
  const thanks = await getThanksSettings();
  thanksEnabled.checked = thanks.enabled;
  thanksTemplate.value = thanks.template;
  const scheduleRes = await send({ type: "GET_SCHEDULE" });
  const schedule = scheduleRes.schedule;
  scheduleEnabled.checked = Boolean(schedule?.enabled ?? scheduleRes.scheduleEnabled);
  scheduleStart.value = schedule?.startAt ?? "";
  scheduleRepeat.value = schedule?.repeat ?? "daily";
  const unfollowScheduleRes = await send({ type: "GET_UNFOLLOW_SCHEDULE" });
  const unfollowSchedule = unfollowScheduleRes.unfollowSchedule;
  unfollowScheduleEnabled.checked = Boolean(unfollowSchedule?.enabled);
  unfollowScheduleStart.value = unfollowSchedule?.startAt ?? "";
  unfollowScheduleRepeat.value = unfollowSchedule?.repeat ?? "weekly";
  updateCount();
})();
