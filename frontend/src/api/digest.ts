import { fetchPublicJson } from "./client";
import type { PublicArticle } from "./articles";
export type { PublicArticle, PublicSource } from "./articles";

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
