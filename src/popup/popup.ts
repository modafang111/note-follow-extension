import type { JobState, RuntimeMessage, RuntimeResponse } from "../types";

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
    name.textContent = log.urlname || "システム";
    const msg = document.createElement("div");
    msg.className = log.status;
    msg.textContent = log.message;
    li.append(name, msg);
    logList.append(li);
  }
}

async function refresh(): Promise<void> {
  const res = await send({ type: "GET_JOB" });
  if (res.job) render(res.job, res.error);
}

startBtn.addEventListener("click", () => {
  void (async () => {
    startBtn.disabled = true;
    const res = await send({ type: "START_FOLLOW" });
    const job = res.job ?? (await send({ type: "GET_JOB" })).job;
    if (job) render(job, res.ok ? undefined : res.error);
    else startBtn.disabled = false;
  })();
});

stopBtn.addEventListener("click", () => {
  void (async () => {
    const res = await send({ type: "STOP_FOLLOW" });
    if (res.job) render(res.job, res.error);
  })();
});

optionsBtn.addEventListener("click", () => {
  void chrome.runtime.openOptionsPage();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local" || !changes.job) return;
  const job = changes.job.newValue as JobState | undefined;
  if (job) render(job);
});

void refresh();
