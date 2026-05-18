import type { FolderNode, MediaFile, MediaListResponse, MediaQuery } from '../types/media';

const API_BASE = '/api';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function getMedia(query: MediaQuery = {}): Promise<MediaListResponse> {
  const params = new URLSearchParams();
  if (query.page) params.set('page', String(query.page));
  if (query.per_page) params.set('per_page', String(query.per_page));
  if (query.media_type) params.set('media_type', query.media_type);
  if (query.folder) params.set('folder', query.folder);
  if (query.search) params.set('search', query.search);
  if (query.checkpoint) params.set('checkpoint', query.checkpoint);
  if (query.sampler) params.set('sampler', query.sampler);
  if (query.sort_by) params.set('sort_by', query.sort_by);
  if (query.sort_order) params.set('sort_order', query.sort_order);
  return fetchJson<MediaListResponse>(`${API_BASE}/media?${params}`);
}

export async function getMediaById(id: number): Promise<MediaFile> {
  return fetchJson<MediaFile>(`${API_BASE}/media/${id}`);
}

export async function getFolderTree(): Promise<FolderNode[]> {
  return fetchJson<FolderNode[]>(`${API_BASE}/media/folders/tree`);
}

export async function triggerScan(): Promise<{ status: string; stats: Record<string, number> }> {
  const res = await fetch(`${API_BASE}/scan`, { method: 'POST' });
  if (!res.ok) {
    throw new Error(`Scan failed: ${res.status}`);
  }
  return res.json();
}

export function getMediaFileUrl(filePath: string): string {
  return `${API_BASE}/media/file/${filePath}`;
}

export function getThumbnailUrl(thumbnailUrl: string): string {
  return thumbnailUrl;
}
