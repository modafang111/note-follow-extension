export type JobStatus = "idle" | "running" | "stopped" | "completed";

export type LogStatus = "followed" | "skipped" | "error" | "info";

export type JobLog = {
  urlname: string;
  status: LogStatus;
  message: string;
  at: number;
};

export type JobState = {
  status: JobStatus;
  queue: string[];
  current: string | null;
  processed: number;
  total: number;
  followed: number;
  skipped: number;
  failed: number;
  logs: JobLog[];
  error: string | null;
};

export type FollowDecision = "follow" | "skip-following" | "skip-myself";

export type Creator = {
  id: number;
  key: string;
  urlname: string;
  nickname?: string;
  isFollowing: boolean;
  isMyself: boolean;
};

export type RuntimeMessage =
  | { type: "START_FOLLOW" }
  | { type: "STOP_FOLLOW" }
  | { type: "GET_JOB" };

export type RuntimeResponse = {
  ok: boolean;
  error?: string;
  job?: JobState;
};
