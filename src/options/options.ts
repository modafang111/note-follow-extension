import { getUrlnamesText, setUrlnamesText } from "../lib/storage";
import { parseUrlnames } from "../lib/urlnames";

const textarea = document.querySelector<HTMLTextAreaElement>("#urlnames")!;
const saveBtn = document.querySelector<HTMLButtonElement>("#save-btn")!;
const savedEl = document.querySelector<HTMLElement>("#saved")!;
const countEl = document.querySelector<HTMLElement>("#count")!;

function updateCount(): void {
  const n = parseUrlnames(textarea.value).length;
  countEl.textContent = `${n} 人`;
}

textarea.addEventListener("input", updateCount);

saveBtn.addEventListener("click", () => {
  void (async () => {
    await setUrlnamesText(textarea.value);
    updateCount();
    savedEl.hidden = false;
    window.setTimeout(() => {
      savedEl.hidden = true;
    }, 1600);
  })();
});

void (async () => {
  textarea.value = await getUrlnamesText();
  updateCount();
})();
