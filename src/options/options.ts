import {
  getThanksSettings,
  getUrlnamesText,
  setThanksSettings,
  setUrlnamesText,
} from "../lib/storage";
import { DEFAULT_THANKS_TEMPLATE } from "../lib/thanks";
import { parseUrlnames } from "../lib/urlnames";

const textarea = document.querySelector<HTMLTextAreaElement>("#urlnames")!;
const saveBtn = document.querySelector<HTMLButtonElement>("#save-btn")!;
const savedEl = document.querySelector<HTMLElement>("#saved")!;
const countEl = document.querySelector<HTMLElement>("#count")!;
const thanksEnabled = document.querySelector<HTMLInputElement>("#thanks-enabled")!;
const thanksTemplate = document.querySelector<HTMLTextAreaElement>("#thanks-template")!;

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
    updateCount();
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
  updateCount();
})();
