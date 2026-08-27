import type { JobState, RuntimeMessage, RuntimeResponse, ThanksItem } from "../types";
import { formatDateTime } from "../lib/schedule-time";

const importBtn = document.querySelector<HTMLButtonElement>("#import-btn")!;
const testBtn = document.querySelector<HTMLButtonElement>("#test-btn")!;
const startBtn = document.querySelector<HTMLButtonElement>("#start-btn")!;
const stopBtn = document.querySelector<HTMLButtonElement>("#stop-btn")!;
const optionsBtn = document.querySelector<HTMLButtonElement>("#options-btn")!;
const statusBadge = document.querySelector<HTMLElement>("#status-badge")!;
const progressLabel = document.querySelector<HTMLElement>("#progress-label")!;
const currentLabel = document.querySelector<HTMLElement>("#current-label")!;
const barFill = document.querySelector<HTMLElement>("#bar-fill")!;
const followedEl = document.querySelector<HTMLElement>("#followed")!;
const skippedEl = document.querySelector<HTMLElement>("#skipped")!;
const failedEl = document.querySelector<HTMLElement>("#failed")!;
const logList = document.querySelector<HTMLUListElement>("#log-list")!;
const errorEl = document.querySelector<HTMLElement>("#error")!;
const thanksBlock = document.querySelector<HTMLElement>("#thanks-block")!;
const thanksMeta = document.querySelector<HTMLElement>("#thanks-meta")!;
const thanksPreview = document.querySelector<HTMLElement>("#thanks-preview")!;
const thanksOpen = document.querySelector<HTMLButtonElement>("#thanks-open")!;
const thanksSkip = document.querySelector<HTMLButtonElement>("#thanks-skip")!;
const scheduleNext = document.querySelector<HTMLElement>("#schedule-next")!;
const lastRun = document.querySelector<HTMLElement>("#last-run")!;

const STATUS_LABEL: Record<JobState["status"], string> = {
  idle: "待機中",
  running: "実行中",
  stopped: "停止",
  completed: "完了",
};

function send(message: RuntimeMessage): Promise<RuntimeResponse> {
  return chrome.runtime.sendMessage(message);
}

function render(job: JobState, error?: string): void {
  statusBadge.textContent = STATUS_LABEL[job.status];
  statusBadge.className = `badge ${job.status}`;

  const running = job.status === "running";
  importBtn.disabled = running;
  testBtn.disabled = running;
  startBtn.disabled = running;
  stopBtn.disabled = !running;

  const total = job.total || 0;
  const processed = job.processed || 0;
  progressLabel.textContent = `${processed} / ${total}`;
  currentLabel.textContent = job.current ? `処理中: ${job.current}` : "";
  barFill.style.width = total === 0 ? "0%" : `${Math.round((processed / total) * 100)}%`;

  followedEl.textContent = String(job.followed);
  skippedEl.textContent = String(job.skipped);
  failedEl.textContent = String(job.failed);

  if (job.status === "running" && job.startedAt) {
    lastRun.textContent = `開始: ${formatDateTime(job.startedAt)}`;
  } else if (job.finishedAt) {
    lastRun.textContent = `終了: ${formatDateTime(job.finishedAt)}`;
  } else {
    lastRun.textContent = "終了: まだありません";
  }

  const message = error || job.error;
  errorEl.hidden = !message;
  errorEl.textContent = message ?? "";

  logList.replaceChildren();
  if (job.logs.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "まだログはありません";
    logList.append(empty);
    return;
  }

  for (const log of job.logs) {
    const li = document.createElement("li");
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = `${formatDateTime(log.at)}  ${log.urlname || "システム"}`;
    const msg = document.createElement("div");
    msg.className = log.status;
    msg.textContent = log.message;
    li.append(name, msg);
    logList.append(li);
  }
}

function renderThanks(queue: ThanksItem[], preview: string): void {
  const next = queue[0];
  thanksBlock.hidden = !next;
  if (!next) return;
  thanksMeta.textContent = `次: ${next.nickname} (@${next.urlname})　残り ${queue.length} 人`;
  thanksPreview.textContent = preview;
}

async function refresh(): Promise<void> {
  const [jobRes, thanksRes, scheduleRes] = await Promise.all([
    send({ type: "GET_JOB" }),
    send({ type: "GET_THANKS" }),
    send({ type: "GET_SCHEDULE" }),
  ]);
  if (jobRes.job) render(jobRes.job, jobRes.error);
  renderThanks(thanksRes.thanksQueue ?? [], thanksRes.thanksPreview ?? "");
  scheduleNext.textContent = `次回の自動フォロー: ${scheduleRes.scheduleNextLabel ?? "未設定"}`;
}

importBtn.addEventListener("click", () => {
  void (async () => {
    importBtn.disabled = true;
    testBtn.disabled = true;
    startBtn.disabled = true;
    const res = await send({ type: "IMPORT_FOLLOWERS" });
    const job = res.job ?? (await send({ type: "GET_JOB" })).job;
    if (job) render(job, res.ok ? undefined : res.error);
    else {
      importBtn.disabled = false;
      testBtn.disabled = false;
      startBtn.disabled = false;
    }
  })();
});

testBtn.addEventListener("click", () => {
  void (async () => {
    testBtn.disabled = true;
    const res = await send({ type: "TEST_FOLLOW" });
    const job = res.job ?? (await send({ type: "GET_JOB" })).job;
    if (job) render(job, res.ok ? undefined : res.error);
    testBtn.disabled = job?.status === "running";
  })();
});

startBtn.addEventListener("click", () => {
  void (async () => {
    startBtn.disabled = true;
    importBtn.disabled = true;
    testBtn.disabled = true;
    const res = await send({ type: "START_FOLLOW" });
    const job = res.job ?? (await send({ type: "GET_JOB" })).job;
    if (job) render(job, res.ok ? undefined : res.error);
    else {
      startBtn.disabled = false;
      importBtn.disabled = false;
      testBtn.disabled = false;
    }
  })();
});

stopBtn.addEventListener("click", () => {
  void (async () => {
    const res = await send({ type: "STOP_FOLLOW" });
    if (res.job) render(res.job, res.error);
  })();
});

thanksOpen.addEventListener("click", () => {
  void (async () => {
    const current = thanksPreview.textContent ?? "";
    try {
      if (current) await navigator.clipboard.writeText(current);
    } catch {
      // コピーに失敗しても画面オープンは続ける
    }
    const res = await send({ type: "OPEN_NEXT_THANKS" });
    renderThanks(res.thanksQueue ?? [], res.thanksPreview ?? "");
    if (!res.ok && res.error) {
      errorEl.hidden = false;
      errorEl.textContent = res.error;
    }
  })();
});

thanksSkip.addEventListener("click", () => {
  void (async () => {
    const res = await send({ type: "SKIP_THANKS" });
    renderThanks(res.thanksQueue ?? [], res.thanksPreview ?? "");
  })();
});

optionsBtn.addEventListener("click", () => {
  void chrome.runtime.openOptionsPage();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.job?.newValue) {
    render(changes.job.newValue as JobState);
  }
  if (changes.thanksQueue) {
    void refresh();
  }
});

void refresh();
