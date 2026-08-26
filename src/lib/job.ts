import type { JobLog, JobState, RuntimeMessage, RuntimeResponse } from "../types";
import { assertLoggedIn, fetchCreator, followUser, NoteApiError } from "./note-api";
import { EMPTY_JOB, getJob, getUrlnamesText, setJob } from "./storage";
import { decideFollowAction, parseUrlnames, randomDelayMs } from "./urlnames";

export const FOLLOW_ALARM = "note-follow-next";
const MAX_LOGS = 80;

let processing = false;

function prependLog(job: JobState, log: Omit<JobLog, "at">): void {
  job.logs = [{ ...log, at: Date.now() }, ...job.logs].slice(0, MAX_LOGS);
}

export async function startFollowJob(): Promise<JobState> {
  const current = await getJob();
  if (current.status === "running") {
    return current;
  }

  const urlnames = parseUrlnames(await getUrlnamesText());
  if (urlnames.length === 0) {
    throw new Error("フォロー対象の urlname がありません。オプションで入力してください。");
  }

  await chrome.alarms.clear(FOLLOW_ALARM);
  await assertLoggedIn();

  const job: JobState = {
    ...EMPTY_JOB,
    status: "running",
    queue: [...urlnames],
    total: urlnames.length,
  };
  prependLog(job, {
    urlname: "",
    status: "info",
    message: `${urlnames.length} 件のフォローを開始します`,
  });
  await setJob(job);
  await processNext();
  return getJob();
}

export async function stopFollowJob(): Promise<JobState> {
  await chrome.alarms.clear(FOLLOW_ALARM);
  const job = await getJob();
  if (job.status === "running") {
    job.status = "stopped";
    job.current = null;
    job.error = null;
    prependLog(job, {
      urlname: "",
      status: "info",
      message: "停止しました",
    });
    await setJob(job);
  }
  return getJob();
}

export async function processNext(): Promise<void> {
  if (processing) return;
  processing = true;

  try {
    const job = await getJob();
    if (job.status !== "running") return;

    const urlname = job.queue.shift();
    if (!urlname) {
      job.status = "completed";
      job.current = null;
      prependLog(job, {
        urlname: "",
        status: "info",
        message: "完了しました",
      });
      await setJob(job);
      return;
    }

    job.current = urlname;
    await setJob(job);

    try {
      const creator = await fetchCreator(urlname);
      const action = decideFollowAction(creator);

      if (action === "skip-following") {
        job.skipped += 1;
        prependLog(job, {
          urlname,
          status: "skipped",
          message: "既にフォロー済みのためスキップ",
        });
      } else if (action === "skip-myself") {
        job.skipped += 1;
        prependLog(job, {
          urlname,
          status: "skipped",
          message: "自分自身のためスキップ",
        });
      } else {
        await followUser(creator.key);
        job.followed += 1;
        prependLog(job, {
          urlname,
          status: "followed",
          message: creator.nickname
            ? `${creator.nickname} をフォローしました`
            : "フォローしました",
        });
      }
    } catch (error) {
      job.failed += 1;
      const message =
        error instanceof NoteApiError || error instanceof Error
          ? error.message
          : String(error);
      prependLog(job, { urlname, status: "error", message });

      if (message.includes("ログイン")) {
        job.status = "stopped";
        job.current = null;
        job.error = message;
        await setJob(job);
        await chrome.alarms.clear(FOLLOW_ALARM);
        return;
      }
    }

    job.processed += 1;
    job.current = null;

    if (job.queue.length === 0) {
      job.status = "completed";
      prependLog(job, {
        urlname: "",
        status: "info",
        message: "完了しました",
      });
      await setJob(job);
      return;
    }

    await setJob(job);
    const delay = randomDelayMs(3000, 5000);
    await chrome.alarms.create(FOLLOW_ALARM, { when: Date.now() + delay });
  } finally {
    processing = false;
  }
}

export async function resumeIfNeeded(): Promise<void> {
  const job = await getJob();
  if (job.status !== "running") return;
  const existing = await chrome.alarms.get(FOLLOW_ALARM);
  if (!existing) {
    await chrome.alarms.create(FOLLOW_ALARM, { when: Date.now() + 500 });
  }
}

export async function handleMessage(
  message: RuntimeMessage,
): Promise<RuntimeResponse> {
  try {
    if (message.type === "GET_JOB") {
      return { ok: true, job: await getJob() };
    }
    if (message.type === "START_FOLLOW") {
      return { ok: true, job: await startFollowJob() };
    }
    if (message.type === "STOP_FOLLOW") {
      return { ok: true, job: await stopFollowJob() };
    }
    return { ok: false, error: "不明なメッセージです" };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : String(error),
      job: await getJob(),
    };
  }
}
