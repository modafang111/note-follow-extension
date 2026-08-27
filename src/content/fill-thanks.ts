import {
  getPendingThanksFill,
  setPendingThanksFill,
} from "../lib/storage";

const BUTTON_LABELS = ["メッセージ", "Message"];

function pathUrlname(): string | null {
  const part = location.pathname.replace(/^\/+/, "").split("/")[0];
  return part || null;
}

function matchesTarget(urlname: string): boolean {
  const current = pathUrlname();
  return current?.toLowerCase() === urlname.toLowerCase();
}

function isVisible(el: Element): boolean {
  const node = el as HTMLElement;
  if (node.offsetParent === null && node.style.position !== "fixed") return false;
  const rect = node.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function labelOf(el: Element): string {
  const node = el as HTMLElement;
  return (
    node.getAttribute("aria-label") ||
    node.getAttribute("title") ||
    node.textContent ||
    ""
  )
    .replace(/\s+/g, " ")
    .trim();
}

function findMessageButton(): HTMLElement | null {
  const candidates = Array.from(
    document.querySelectorAll<HTMLElement>("button, a, [role='button']"),
  );
  for (const el of candidates) {
    if (!isVisible(el)) continue;
    const label = labelOf(el);
    if (BUTTON_LABELS.some((name) => label === name || label.includes(name))) {
      if (label.includes("お問い合わせ")) continue;
      return el;
    }
  }
  return null;
}

function findComposer(): HTMLTextAreaElement | HTMLElement | null {
  const textarea = document.querySelector<HTMLTextAreaElement>(
    "textarea:not([disabled])",
  );
  if (textarea && isVisible(textarea)) return textarea;

  const boxes = Array.from(
    document.querySelectorAll<HTMLElement>(
      '[contenteditable="true"], [role="textbox"]',
    ),
  );
  for (const el of boxes) {
    if (isVisible(el)) return el;
  }
  return null;
}

function setComposerValue(el: HTMLElement, value: string): void {
  el.focus();
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) {
    const proto = Object.getPrototypeOf(el) as { value?: unknown };
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc?.set) desc.set.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }

  el.textContent = value;
  el.dispatchEvent(
    new InputEvent("input", {
      bubbles: true,
      data: value,
      inputType: "insertText",
    }),
  );
}

function showToast(text: string): void {
  const id = "note-follow-thanks-toast";
  document.getElementById(id)?.remove();
  const toast = document.createElement("div");
  toast.id = id;
  toast.textContent = text;
  toast.style.cssText = [
    "position:fixed",
    "z-index:2147483647",
    "right:16px",
    "bottom:16px",
    "max-width:320px",
    "padding:12px 14px",
    "border-radius:10px",
    "background:#1f8f75",
    "color:#fff",
    "font:13px/1.5 sans-serif",
    "box-shadow:0 6px 20px rgba(0,0,0,.2)",
  ].join(";");
  document.body.append(toast);
  window.setTimeout(() => toast.remove(), 6000);
}

async function waitFor<T>(
  find: () => T | null,
  timeoutMs: number,
): Promise<T | null> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const found = find();
    if (found) return found;
    await new Promise((resolve) => window.setTimeout(resolve, 250));
  }
  return find();
}

async function fillThanks(): Promise<void> {
  const pending = await getPendingThanksFill();
  if (!pending || !matchesTarget(pending.urlname)) return;

  try {
    await navigator.clipboard.writeText(pending.body);
  } catch {
    // 権限やフォーカスで失敗しても本文挿入は続ける
  }

  const button = await waitFor(findMessageButton, 8000);
  if (button) {
    button.click();
  }

  const composer = await waitFor(findComposer, button ? 5000 : 1500);
  if (composer) {
    setComposerValue(composer, pending.body);
    showToast("お礼文を入力しました。内容を確認して送信してください。");
    await setPendingThanksFill(null);
    return;
  }

  showToast(
    "メッセージ欄を自動入力できませんでした。本文はクリップボードにコピー済みです。相互フォローと相手の受信設定を確認してください。",
  );
}

void fillThanks();
