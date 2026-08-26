import type { JobState } from "../types";

const URLNAMES_KEY = "urlnamesText";
const JOB_KEY = "job";

export const EMPTY_JOB: JobState = {
  status: "idle",
  queue: [],
  current: null,
  processed: 0,
  total: 0,
  followed: 0,
  skipped: 0,
  failed: 0,
  logs: [],
  error: null,
};

export async function getUrlnamesText(): Promise<string> {
  const result = await chrome.storage.local.get(URLNAMES_KEY);
  return typeof result[URLNAMES_KEY] === "string" ? result[URLNAMES_KEY] : "";
}

export async function setUrlnamesText(text: string): Promise<void> {
  await chrome.storage.local.set({ [URLNAMES_KEY]: text });
}

export async function getJob(): Promise<JobState> {
  const result = await chrome.storage.local.get(JOB_KEY);
  const job = result[JOB_KEY] as JobState | undefined;
  return job ? { ...EMPTY_JOB, ...job } : { ...EMPTY_JOB };
}

export async function setJob(job: JobState): Promise<void> {
  await chrome.storage.local.set({ [JOB_KEY]: job });
}
