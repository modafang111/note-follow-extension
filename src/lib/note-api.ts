import type { Creator, CurrentUser, Follower, FollowersPage } from "../types";

const API_ORIGIN = "https://note.com";

export class NoteApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "NoteApiError";
  }
}

function unwrapData<T>(json: unknown): T {
  if (json && typeof json === "object" && "data" in json) {
    return (json as { data: T }).data;
  }
  return json as T;
}

async function getXsrfToken(): Promise<string | undefined> {
  const cookie = await chrome.cookies.get({
    url: `${API_ORIGIN}/`,
    name: "XSRF-TOKEN",
  });
  if (!cookie?.value) return undefined;
  try {
    return decodeURIComponent(cookie.value);
  } catch {
    return cookie.value;
  }
}

async function buildCookieHeader(): Promise<string> {
  const cookies = await chrome.cookies.getAll({ url: `${API_ORIGIN}/` });
  return cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join("; ");
}

function formatApiError(body: unknown): string {
  if (body == null) return "不明なエラー";
  if (typeof body === "string") return body;
  if (typeof body !== "object") return String(body);

  const record = body as Record<string, unknown>;
  if ("error" in record) return formatApiError(record.error);
  if (typeof record.message === "string") return record.message;
  if (typeof record.code === "string" && typeof record.message === "string") {
    return `${record.code}: ${record.message}`;
  }

  try {
    return JSON.stringify(body);
  } catch {
    return String(body);
  }
}

export async function noteFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = await getXsrfToken();
  const cookieHeader = await buildCookieHeader();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Requested-With", "XMLHttpRequest");
  headers.set("Origin", API_ORIGIN);
  headers.set("Referer", `${API_ORIGIN}/`);
  if (cookieHeader) {
    headers.set("Cookie", cookieHeader);
  }
  if (token) {
    headers.set("X-XSRF-TOKEN", token);
    headers.set("X-CSRF-Token", token);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return fetch(`${API_ORIGIN}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
}

async function readJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

export async function assertLoggedIn(): Promise<void> {
  const cookies = await chrome.cookies.getAll({ domain: "note.com" });
  const hasSession = cookies.some((cookie) =>
    cookie.name.toLowerCase().includes("session"),
  );
  if (!hasSession) {
    throw new NoteApiError("note.com にログインしてから実行してください");
  }
}

export async function fetchCreator(urlname: string): Promise<Creator> {
  const res = await noteFetch(`/api/v2/creators/${encodeURIComponent(urlname)}`);

  if (res.status === 401 || res.status === 403) {
    throw new NoteApiError(
      "note.com にログインしてから実行してください",
      res.status,
    );
  }
  if (res.status === 404) {
    throw new NoteApiError(`ユーザーが見つかりません: ${urlname}`, 404);
  }
  if (!res.ok) {
    throw new NoteApiError(
      `プロフィール取得に失敗しました (${res.status})`,
      res.status,
    );
  }

  const data = unwrapData<Record<string, unknown>>(await readJson(res));
  const id = Number(data?.id);
  const key = typeof data?.key === "string" ? data.key.trim() : "";
  if (!Number.isFinite(id)) {
    throw new NoteApiError(`数値 ID を取得できません: ${urlname}`);
  }
  if (!key) {
    throw new NoteApiError(`ユーザー key を取得できません: ${urlname}`);
  }

  return {
    id,
    key,
    urlname: String(data.urlname ?? urlname),
    nickname: typeof data.nickname === "string" ? data.nickname : undefined,
    isFollowing: Boolean(data.isFollowing ?? data.is_following),
    isMyself: Boolean(data.isMyself ?? data.is_myself),
  };
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  const res = await noteFetch("/api/v2/current_user");
  if (res.status === 401 || res.status === 403) {
    throw new NoteApiError(
      "note.com にログインしてから実行してください",
      res.status,
    );
  }
  if (!res.ok) {
    throw new NoteApiError(`ログインユーザーの取得に失敗しました (${res.status})`, res.status);
  }

  const json = await readJson(res);
  const data = unwrapData<Record<string, unknown>>(json);
  const user = (
    data && typeof data.user === "object" && data.user
      ? data.user
      : data
  ) as Record<string, unknown> | string | null;

  if (!user || typeof user !== "object") {
    throw new NoteApiError("ログインユーザーの取得に失敗しました");
  }

  const urlname = typeof user.urlname === "string" ? user.urlname : "";
  const id = Number(user.id);
  const key = typeof user.key === "string" ? user.key.trim() : "";
  if (!urlname) {
    throw new NoteApiError("自分の urlname を取得できません");
  }

  return {
    id: Number.isFinite(id) ? id : 0,
    key,
    urlname,
    nickname: typeof user.nickname === "string" ? user.nickname : undefined,
  };
}

export async function fetchFollowersPage(
  urlname: string,
  page: number,
): Promise<FollowersPage> {
  const res = await noteFetch(
    `/api/v2/creators/${encodeURIComponent(urlname)}/followers?page=${page}`,
  );
  if (res.status === 401 || res.status === 403) {
    throw new NoteApiError(
      "note.com にログインしてから実行してください",
      res.status,
    );
  }
  if (!res.ok) {
    throw new NoteApiError(`フォロワー取得に失敗しました (${res.status})`, res.status);
  }

  const data = unwrapData<Record<string, unknown>>(await readJson(res));
  const raw = Array.isArray(data?.follows) ? data.follows : [];
  const follows: Follower[] = raw.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    const name = typeof record.urlname === "string" ? record.urlname : "";
    if (!name) return [];
    return [
      {
        urlname: name,
        nickname: typeof record.nickname === "string" ? record.nickname : undefined,
        isFollowing: Boolean(record.isFollowing ?? record.is_following),
      },
    ];
  });

  return {
    follows,
    isLastPage: Boolean(data?.isLastPage ?? data?.is_last_page ?? follows.length === 0),
    totalCount: Number(data?.totalCount ?? data?.total_count ?? follows.length) || follows.length,
  };
}

export async function followUser(userKey: string): Promise<void> {
  const res = await noteFetch(`/api/v3/users/${encodeURIComponent(userKey)}/following`, {
    method: "POST",
  });

  if (res.status === 401 || res.status === 403) {
    throw new NoteApiError(
      "note.com にログインしてから実行してください",
      res.status,
    );
  }

  // 既フォローはスキップ扱い（呼び出し側でも isFollowing を見る）
  if (res.status === 409) return;

  if (res.status !== 200 && res.status !== 201 && res.status !== 204) {
    const body = await readJson(res);
    const detail = body == null ? `HTTP ${res.status}` : formatApiError(body);
    throw new NoteApiError(`フォローに失敗しました: ${detail}`, res.status);
  }
}
