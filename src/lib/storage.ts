import type { JobState, PendingThanksFill, ThanksItem, ThanksSettings } from "../types";
import { DEFAULT_THANKS_SETTINGS } from "./thanks";

const URLNAMES_KEY = "urlnamesText";
const JOB_KEY = "job";
const THANKS_SETTINGS_KEY = "thanksSettings";
const THANKS_QUEUE_KEY = "thanksQueue";
const PENDING_THANKS_KEY = "pendingThanksFill";

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

export async function getThanksSettings(): Promise<ThanksSettings> {
  const result = await chrome.storage.local.get(THANKS_SETTINGS_KEY);
  const stored = result[THANKS_SETTINGS_KEY] as Partial<ThanksSettings> | undefined;
  return {
    ...DEFAULT_THANKS_SETTINGS,
    ...stored,
    template:
      typeof stored?.template === "string" && stored.template.trim()
        ? stored.template
        : DEFAULT_THANKS_SETTINGS.template,
    enabled: stored?.enabled ?? DEFAULT_THANKS_SETTINGS.enabled,
  };
}

export async function setThanksSettings(settings: ThanksSettings): Promise<void> {
  await chrome.storage.local.set({ [THANKS_SETTINGS_KEY]: settings });
}

export async function getThanksQueue(): Promise<ThanksItem[]> {
  const result = await chrome.storage.local.get(THANKS_QUEUE_KEY);
  return Array.isArray(result[THANKS_QUEUE_KEY])
    ? (result[THANKS_QUEUE_KEY] as ThanksItem[])
    : [];
}

export async function setThanksQueue(queue: ThanksItem[]): Promise<void> {
  await chrome.storage.local.set({ [THANKS_QUEUE_KEY]: queue });
}

export async function getPendingThanksFill(): Promise<PendingThanksFill | null> {
  const result = await chrome.storage.local.get(PENDING_THANKS_KEY);
  const pending = result[PENDING_THANKS_KEY] as PendingThanksFill | undefined;
  return pending?.urlname && pending.body ? pending : null;
}

export async function setPendingThanksFill(
  pending: PendingThanksFill | null,
): Promise<void> {
  if (pending) {
    await chrome.storage.local.set({ [PENDING_THANKS_KEY]: pending });
  } else {
    await chrome.storage.local.remove(PENDING_THANKS_KEY);
  }
}
