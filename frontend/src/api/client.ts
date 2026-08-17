export class PublicApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "PublicApiError";
  }
}

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export async function fetchPublicJson<T>(path: string, fetcher: Fetcher = fetch): Promise<T> {
  let url: URL;
  try {
    url = new URL(path, "https://public-api.invalid");
  } catch {
    throw new PublicApiError(0, "invalid_public_path", "公共内容服务暂不可用");
  }
  if (url.origin !== "https://public-api.invalid" || !url.pathname.startsWith("/api/public/")) {
    throw new PublicApiError(0, "invalid_public_path", "公共内容服务暂不可用");
  }

  let response: Response;
  try {
    response = await fetcher(path, { credentials: "omit" });
  } catch {
    // 浏览器网络异常没有可用的 HTTP 响应，仍需保留可显示且可重试的稳定语义。
    throw new PublicApiError(0, "network_error", "公共内容服务暂不可用");
  }
  if (response.ok) {
    return (await response.json()) as T;
  }

  const payload: unknown = await response.json().catch(() => null);
  if (
    payload !== null &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "object" &&
    payload.detail !== null &&
    "code" in payload.detail &&
    "message" in payload.detail &&
    typeof payload.detail.code === "string" &&
    typeof payload.detail.message === "string"
  ) {
    throw new PublicApiError(response.status, payload.detail.code, payload.detail.message);
  }

  throw new PublicApiError(response.status, "request_failed", "公共内容服务暂不可用");
}
