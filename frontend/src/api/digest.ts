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

export interface DigestItem {
  position: number;
  core_summary: string;
  importance: string;
  trend: string;
  topic_label: string | null;
  article: PublicArticle;
}

export interface GitHubProject {
  position: number;
  full_name: string;
  recommendation: string;
}

export interface DigestPublic {
  date: string;
  version: number;
  published_at: string;
  daily_judgement: string;
  items: DigestItem[];
  github_projects: GitHubProject[];
}

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export function getCurrentDigest(fetcher?: Fetcher): Promise<DigestPublic> {
  return fetchPublicJson<DigestPublic>("/api/public/digests", fetcher);
}
