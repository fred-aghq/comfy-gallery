export interface MediaFile {
  id: number;
  file_path: string;
  file_name: string;
  file_extension: string;
  media_type: 'image' | 'video';
  file_size: number;
  width: number | null;
  height: number | null;
  thumbnail_url: string | null;
  checkpoint_name: string | null;
  positive_prompt: string | null;
  negative_prompt: string | null;
  sampler_name: string | null;
  scheduler: string | null;
  cfg_scale: number | null;
  steps: number | null;
  seed: number | null;
  lora_names: string[] | null;
  metadata_prompt: Record<string, unknown> | null;
  metadata_workflow: Record<string, unknown> | null;
  file_created_at: string | null;
  file_modified_at: string | null;
  created_at: string;
}

export interface PaginationMeta {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export interface MediaListResponse {
  items: MediaFile[];
  pagination: PaginationMeta;
}

export interface FolderNode {
  name: string;
  path: string;
  children: FolderNode[];
  file_count: number;
}

export interface MediaQuery {
  page?: number;
  per_page?: number;
  media_type?: 'image' | 'video';
  folder?: string;
  search?: string;
  checkpoint?: string;
  sampler?: string;
  sort_by?: 'file_created_at' | 'file_name' | 'file_size';
  sort_order?: 'asc' | 'desc';
}
