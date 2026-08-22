import { fetchPublicJson } from "./client";

export interface PublicSource {
  name: string;
  display_name: string;
  site_url: string | null;
}

export interface PublicArticle {
  id: number;
  title: string;
  original_url: string;
  category: string;
  topic: string | null;
  summary: string;
  published_at: string | null;
  fetched_at: string;
  source: PublicSource;
}

export interface ArticlePage {
  items: PublicArticle[];
  page: number;
  page_size: number;
  total: number;
}

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export function getArticles(
  options: { source?: string; page?: number } = {},
  fetcher?: Fetcher,
): Promise<ArticlePage> {
  const query = new URLSearchParams();
  if (options.source) query.set("source", options.source);
  if (options.page && options.page > 1) query.set("page", String(options.page));
  const suffix = query.toString();
  return fetchPublicJson<ArticlePage>(`/api/public/articles${suffix ? `?${suffix}` : ""}`, fetcher);
}

export function getSources(fetcher?: Fetcher): Promise<PublicSource[]> {
  return fetchPublicJson<PublicSource[]>("/api/public/sources", fetcher);
}
