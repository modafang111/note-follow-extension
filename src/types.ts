export type JobStatus = "idle" | "running" | "stopped" | "completed";

export type LogStatus = "followed" | "skipped" | "error" | "info";

export type JobLog = {
  urlname: string;
  status: LogStatus;
  message: string;
  at: number;
};

export type ThanksItem = {
  urlname: string;
  nickname: string;
  queuedAt: number;
};

export type ThanksSettings = {
  enabled: boolean;
  template: string;
};

export type PendingThanksFill = {
  urlname: string;
  body: string;
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

export type CurrentUser = {
  id: number;
  key: string;
  urlname: string;
  nickname?: string;
};

export type Follower = {
  urlname: string;
  nickname?: string;
  isFollowing: boolean;
};

export type FollowersPage = {
  follows: Follower[];
  isLastPage: boolean;
  totalCount: number;
};

export type ScheduledJobTrigger = "manual" | "alarm" | "startup";

export type ScheduledJobResult = {
  trigger: ScheduledJobTrigger;
  imported: number;
  started: boolean;
  message: string;
};

export type ScheduleSettings = {
  enabled: boolean;
};

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
  | { type: "GET_JOB" }
  | { type: "GET_THANKS" }
  | { type: "OPEN_NEXT_THANKS" }
  | { type: "SKIP_THANKS" }
  | { type: "IMPORT_FOLLOWERS" }
  | { type: "GET_SCHEDULE" }
  | { type: "SET_SCHEDULE"; enabled: boolean };

export type RuntimeResponse = {
  ok: boolean;
  error?: string;
  job?: JobState;
  thanksQueue?: ThanksItem[];
  thanksPreview?: string;
  thanksOpenedBody?: string;
  scheduled?: ScheduledJobResult;
  scheduleEnabled?: boolean;
};
