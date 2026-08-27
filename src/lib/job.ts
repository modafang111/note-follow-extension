import type { JobLog, JobState, RuntimeMessage, RuntimeResponse } from "../types";
import { assertLoggedIn, fetchCreator, followUser, NoteApiError } from "./note-api";
import {
  EMPTY_JOB,
  addCompletedUrlname,
  getCompletedUrlnames,
  getJob,
  getUrlnamesText,
  setJob,
} from "./storage";
import { decideFollowAction, parseUrlnames, randomDelayMs } from "./urlnames";
import { notifyJobFinished, syncJobBadge } from "./notify";
import { getThanksState, openNextThanks, skipNextThanks } from "./thanks-actions";
import { queueAndDeliverThanks } from "./thanks-delivery";

export const FOLLOW_ALARM = "note-follow-next";
const MAX_LOGS = 80;

function stampFinished(job: JobState): void {
  job.finishedAt = Date.now();
}

let processing = false;

function prependLog(job: JobState, log: Omit<JobLog, "at">): void {
  job.logs = [{ ...log, at: Date.now() }, ...job.logs].slice(0, MAX_LOGS);
}

export async function appendJobInfo(message: string): Promise<void> {
  const job = await getJob();
  prependLog(job, { urlname: "", status: "info", message });
  await setJob(job);
}

export async function startFollowJob(): Promise<JobState> {
  const current = await getJob();
  if (current.status === "running") {
    return current;
  }

  const completed = new Set(
    (await getCompletedUrlnames()).map((name) => name.toLowerCase()),
  );
  const urlnames = parseUrlnames(await getUrlnamesText()).filter(
    (name) => !completed.has(name.toLowerCase()),
  );
  if (urlnames.length === 0) {
    throw new Error("フォロー対象の urlname がありません。オプションで入力するか、フォロワーを取り込んでください。");
  }

  await chrome.alarms.clear(FOLLOW_ALARM);
  await assertLoggedIn();

  const job: JobState = {
    ...EMPTY_JOB,
    status: "running",
    queue: [...urlnames],
    total: urlnames.length,
    startedAt: Date.now(),
    finishedAt: null,
  };
  prependLog(job, {
    urlname: "",
    status: "info",
    message: `${urlnames.length} 件のフォローを開始します`,
  });
  await setJob(job);
  await syncJobBadge(job);
  await processNext();
  return getJob();
}

export async function appendToRunningQueue(urlnames: string[]): Promise<number> {
  const job = await getJob();
  if (job.status !== "running") return 0;

  const have = new Set(
    [...job.queue, job.current ?? ""].map((name) => name.toLowerCase()).filter(Boolean),
  );
  const extra = urlnames.filter((name) => {
    const key = name.trim().toLowerCase();
    if (!key || have.has(key)) return false;
    have.add(key);
    return true;
  });
  if (extra.length === 0) return 0;

  job.queue.push(...extra);
  job.total += extra.length;
  prependLog(job, {
    urlname: "",
    status: "info",
    message: `実行中のキューに ${extra.length} 人を追加しました`,
  });
  await setJob(job);
  return extra.length;
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
    stampFinished(job);
    await setJob(job);
    await notifyJobFinished(job);
  } else {
    await syncJobBadge(job);
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
      stampFinished(job);
      await setJob(job);
      await notifyJobFinished(job);
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
        await addCompletedUrlname(urlname);
      } else if (action === "skip-myself") {
        job.skipped += 1;
        prependLog(job, {
          urlname,
          status: "skipped",
          message: "自分自身のためスキップ",
        });
        await addCompletedUrlname(urlname);
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
        await queueAndDeliverThanks({
          urlname: creator.urlname || urlname,
          nickname: creator.nickname || urlname,
        });
        await addCompletedUrlname(urlname);
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
        stampFinished(job);
        await setJob(job);
        await chrome.alarms.clear(FOLLOW_ALARM);
        await notifyJobFinished(job);
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
      stampFinished(job);
      await setJob(job);
      await notifyJobFinished(job);
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
  await syncJobBadge(job);
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
    if (message.type === "GET_THANKS") {
      const state = await getThanksState();
      return { ok: true, thanksQueue: state.queue, thanksPreview: state.preview };
    }
    if (message.type === "OPEN_NEXT_THANKS") {
      return openNextThanks();
    }
    if (message.type === "SKIP_THANKS") {
      return skipNextThanks();
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
