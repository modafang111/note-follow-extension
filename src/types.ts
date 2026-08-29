export type JobStatus = "idle" | "running" | "stopped" | "completed";

export type LogStatus = "followed" | "unfollowed" | "skipped" | "error" | "info";

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
  startedAt: number | null;
  finishedAt: number | null;
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

export type UnfollowReason = "withdrawn" | "not-followed";

export type Following = {
  urlname: string;
  key: string;
  nickname?: string;
  isFollowing: boolean;
  isFollowed: boolean;
  withdrawal: boolean;
};

export type FollowingsPage = {
  follows: Following[];
  isLastPage: boolean;
  totalCount: number;
};

export type UnfollowTarget = {
  urlname: string;
  key: string;
  nickname?: string;
  reason: UnfollowReason;
};

export type UnfollowJobState = {
  status: JobStatus;
  queue: UnfollowTarget[];
  current: string | null;
  processed: number;
  total: number;
  unfollowed: number;
  skipped: number;
  failed: number;
  logs: JobLog[];
  error: string | null;
  startedAt: number | null;
  finishedAt: number | null;
};

export type UnfollowJobResult = {
  trigger: "manual" | "test";
  found: number;
  started: boolean;
  message: string;
};

export type ScheduledJobTrigger = "manual" | "alarm" | "startup" | "test";

export type ScheduledJobResult = {
  trigger: ScheduledJobTrigger;
  imported: number;
  started: boolean;
  message: string;
};

export type ScheduleRepeat = "once" | "every-30m" | "hourly" | "daily";

export type ScheduleSettings = {
  enabled: boolean;
  startAt: string;
  repeat: ScheduleRepeat;
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
  | { type: "TEST_FOLLOW" }
  | { type: "GET_SCHEDULE" }
  | { type: "SET_SCHEDULE"; settings: ScheduleSettings }
  | { type: "START_UNFOLLOW" }
  | { type: "STOP_UNFOLLOW" }
  | { type: "TEST_UNFOLLOW" }
  | { type: "GET_UNFOLLOW" }
  | { type: "THANKS_FILL_RESULT"; sent: boolean; error?: string };

export type RuntimeResponse = {
  ok: boolean;
  error?: string;
  job?: JobState;
  thanksQueue?: ThanksItem[];
  thanksPreview?: string;
  thanksOpenedBody?: string;
  thanksTabId?: number;
  scheduled?: ScheduledJobResult;
  schedule?: ScheduleSettings;
  scheduleEnabled?: boolean;
  scheduleNextLabel?: string;
  unfollowJob?: UnfollowJobState;
  unfollow?: UnfollowJobResult;
};
