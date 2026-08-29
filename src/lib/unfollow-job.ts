import type {
  Following,
  JobLog,
  UnfollowJobResult,
  UnfollowJobState,
  UnfollowTarget,
} from "../types";
import {
  assertLoggedIn,
  fetchCurrentUser,
  fetchFollowingsPage,
  NoteApiError,
  unfollowUser,
} from "./note-api";
import {
  addUnfollowedUrlname,
  EMPTY_UNFOLLOW_JOB,
  getJob,
  getUnfollowedUrlnames,
  getUnfollowJob,
  setUnfollowJob,
} from "./storage";
import {
  filterUnfollowTargets,
  formatUnfollowTestPreview,
  orderUnfollowTargetsOldestFirst,
  unfollowReasonLabel,
} from "./followings";
import { randomDelayMs } from "./urlnames";
import { notifyPopup, notifyUnfollowFinished, syncUnfollowBadge } from "./notify";

export const UNFOLLOW_ALARM = "note-unfollow-next";
const MAX_FOLLOWING_PAGES = 80;
const MAX_LOGS = 80;

let processing = false;

function stampFinished(job: UnfollowJobState): void {
  job.finishedAt = Date.now();
}

function prependLog(job: UnfollowJobState, log: Omit<JobLog, "at">): void {
  job.logs = [{ ...log, at: Date.now() }, ...job.logs].slice(0, MAX_LOGS);
}

async function collectUnfollowTargets(): Promise<UnfollowTarget[]> {
  const me = await fetchCurrentUser();
  const all: Following[] = [];
  for (let page = 1; page <= MAX_FOLLOWING_PAGES; page += 1) {
    const data = await fetchFollowingsPage(me.urlname, page);
    all.push(...data.follows);
    if (data.isLastPage || data.follows.length === 0) break;
  }
  const completed = await getUnfollowedUrlnames();
  return orderUnfollowTargetsOldestFirst(filterUnfollowTargets(all, completed));
}

export async function isUnfollowRunning(): Promise<boolean> {
  return (await getUnfollowJob()).status === "running";
}

export async function isFollowRunning(): Promise<boolean> {
  return (await getJob()).status === "running";
}

export async function runTestUnfollow(): Promise<UnfollowJobResult> {
  if (await isFollowRunning()) {
    throw new Error("フォロー返しの実行中は、解除のテスト実行ができません。終わるまで待ってください。");
  }
  await assertLoggedIn();
  const targets = await collectUnfollowTargets();
  const job = await getUnfollowJob();
  prependLog(job, {
    urlname: "",
    status: "info",
    message: `解除のテスト実行: 対象 ${targets.length} 人。実際の解除はしていません。`,
  });
  for (const target of targets.slice(0, 15)) {
    prependLog(job, {
      urlname: target.urlname,
      status: "info",
      message: `テスト対象: ${unfollowReasonLabel(target.reason)}`,
    });
  }
  if (targets.length > 15) {
    prependLog(job, {
      urlname: "",
      status: "info",
      message: `テスト対象: ほか ${targets.length - 15} 人`,
    });
  }
  await setUnfollowJob(job);
  await notifyPopup(
    "解除のテスト実行が終わりました",
    `対象 ${targets.length} 人。実際の解除はしていません。`,
  );
  return {
    trigger: "test",
    found: targets.length,
    started: false,
    message: formatUnfollowTestPreview(targets),
  };
}

export async function startUnfollowJob(): Promise<UnfollowJobState> {
  const current = await getUnfollowJob();
  if (current.status === "running") {
    return current;
  }
  if (await isFollowRunning()) {
    throw new Error("フォロー返しの実行中は、フォロー解除を開始できません。終わるまで待ってください。");
  }

  await chrome.alarms.clear(UNFOLLOW_ALARM);
  await assertLoggedIn();
  const targets = await collectUnfollowTargets();
  if (targets.length === 0) {
    throw new Error("解除する相手はいませんでした。こちらがフォローしていて、相手がフォローしていない人、または退会した人だけが対象です。");
  }

  const job: UnfollowJobState = {
    ...EMPTY_UNFOLLOW_JOB,
    status: "running",
    queue: [...targets],
    total: targets.length,
    startedAt: Date.now(),
    finishedAt: null,
  };
  prependLog(job, {
    urlname: "",
    status: "info",
    message: `${targets.length} 人のフォロー解除を開始します（退会またはフォローされていない人）`,
  });
  await setUnfollowJob(job);
  await syncUnfollowBadge(job);
  await processUnfollowNext();
  return getUnfollowJob();
}

export async function stopUnfollowJob(): Promise<UnfollowJobState> {
  await chrome.alarms.clear(UNFOLLOW_ALARM);
  const job = await getUnfollowJob();
  if (job.status === "running") {
    job.status = "stopped";
    job.current = null;
    job.error = null;
    prependLog(job, {
      urlname: "",
      status: "info",
      message: "フォロー解除を停止しました",
    });
    stampFinished(job);
    await setUnfollowJob(job);
    await notifyUnfollowFinished(job);
  } else {
    await syncUnfollowBadge(job);
  }
  return getUnfollowJob();
}

export async function processUnfollowNext(): Promise<void> {
  if (processing) return;
  processing = true;

  try {
    const job = await getUnfollowJob();
    if (job.status !== "running") return;

    const target = job.queue.shift();
    if (!target) {
      job.status = "completed";
      job.current = null;
      prependLog(job, {
        urlname: "",
        status: "info",
        message: "フォロー解除が完了しました",
      });
      stampFinished(job);
      await setUnfollowJob(job);
      await notifyUnfollowFinished(job);
      return;
    }

    job.current = target.urlname;
    await setUnfollowJob(job);

    try {
      await unfollowUser(target.key);
      job.unfollowed += 1;
      prependLog(job, {
        urlname: target.urlname,
        status: "unfollowed",
        message: target.nickname
          ? `${target.nickname} のフォローを解除しました（${unfollowReasonLabel(target.reason)}）`
          : `フォローを解除しました（${unfollowReasonLabel(target.reason)}）`,
      });
      await addUnfollowedUrlname(target.urlname);
    } catch (error) {
      job.failed += 1;
      const message =
        error instanceof NoteApiError || error instanceof Error
          ? error.message
          : String(error);
      prependLog(job, { urlname: target.urlname, status: "error", message });

      if (message.includes("ログイン")) {
        job.status = "stopped";
        job.current = null;
        job.error = message;
        stampFinished(job);
        await setUnfollowJob(job);
        await chrome.alarms.clear(UNFOLLOW_ALARM);
        await notifyUnfollowFinished(job);
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
        message: "フォロー解除が完了しました",
      });
      stampFinished(job);
      await setUnfollowJob(job);
      await notifyUnfollowFinished(job);
      return;
    }

    await setUnfollowJob(job);
    const delay = randomDelayMs(3000, 5000);
    await chrome.alarms.create(UNFOLLOW_ALARM, { when: Date.now() + delay });
  } finally {
    processing = false;
  }
}

export async function resumeUnfollowIfNeeded(): Promise<void> {
  const job = await getUnfollowJob();
  await syncUnfollowBadge(job);
  if (job.status !== "running") return;
  const existing = await chrome.alarms.get(UNFOLLOW_ALARM);
  if (!existing) {
    await chrome.alarms.create(UNFOLLOW_ALARM, { when: Date.now() + 500 });
  }
}
