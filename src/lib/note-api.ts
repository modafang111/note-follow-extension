import type { Creator } from "../types";

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

export async function noteFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = await getXsrfToken();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Requested-With", "XMLHttpRequest");
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
  if (!Number.isFinite(id)) {
    throw new NoteApiError(`数値 ID を取得できません: ${urlname}`);
  }

  return {
    id,
    urlname: String(data.urlname ?? urlname),
    nickname: typeof data.nickname === "string" ? data.nickname : undefined,
    isFollowing: Boolean(data.isFollowing ?? data.is_following),
    isMyself: Boolean(data.isMyself ?? data.is_myself),
  };
}

export async function followUser(numericId: number): Promise<void> {
  const res = await noteFetch(`/api/v3/users/${numericId}/following`, {
    method: "POST",
    body: "{}",
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
    const detail =
      typeof body === "object" && body && "error" in body
        ? String((body as { error: unknown }).error)
        : `HTTP ${res.status}`;
    throw new NoteApiError(`フォローに失敗しました: ${detail}`, res.status);
  }
}
