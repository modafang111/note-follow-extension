import {
  getThanksSettings,
  getUrlnamesText,
  setThanksSettings,
  setUrlnamesText,
} from "../lib/storage";
import { DEFAULT_THANKS_TEMPLATE } from "../lib/thanks";
import { parseUrlnames } from "../lib/urlnames";
import type { RuntimeMessage, RuntimeResponse } from "../types";

const textarea = document.querySelector<HTMLTextAreaElement>("#urlnames")!;
const saveBtn = document.querySelector<HTMLButtonElement>("#save-btn")!;
const savedEl = document.querySelector<HTMLElement>("#saved")!;
const countEl = document.querySelector<HTMLElement>("#count")!;
const scheduleEnabled = document.querySelector<HTMLInputElement>("#schedule-enabled")!;
const thanksEnabled = document.querySelector<HTMLInputElement>("#thanks-enabled")!;
const thanksTemplate = document.querySelector<HTMLTextAreaElement>("#thanks-template")!;

function send(message: RuntimeMessage): Promise<RuntimeResponse> {
  return chrome.runtime.sendMessage(message);
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
      enabled: scheduleEnabled.checked,
    });
    if (!scheduleRes.ok) {
      savedEl.hidden = false;
      savedEl.textContent = scheduleRes.error ?? "自動フォローの保存に失敗しました";
      return;
    }
    updateCount();
    savedEl.textContent = "保存しました";
    savedEl.hidden = false;
    window.setTimeout(() => {
      savedEl.hidden = true;
    }, 1600);
  })();
});

void (async () => {
  textarea.value = await getUrlnamesText();
  const thanks = await getThanksSettings();
  thanksEnabled.checked = thanks.enabled;
  thanksTemplate.value = thanks.template;
  const scheduleRes = await send({ type: "GET_SCHEDULE" });
  scheduleEnabled.checked = Boolean(scheduleRes.scheduleEnabled);
  updateCount();
})();
