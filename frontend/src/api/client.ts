/**
 * Thin client for the Shelfie API.
 *
 * Every call funnels through `request`, so a backend that is unreachable
 * surfaces one recognisable error type that screens can render as a retry
 * rather than an unexplained blank state.
 */

const BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL?.replace(/\/$/, '') ?? 'http://localhost:8000';

export type ScanStatus = 'matched' | 'review' | 'unmatched' | 'unreadable' | 'skipped';

export type Candidate = {
  id: string;
  title: string;
  author: string;
  year: string;
  publisher: string;
  score: number;
  title_score: number;
  author_score: number | null;
};

export type ScanItem = {
  id: number;
  index: number;
  box: number[];
  detector_confidence: number | null;
  crop_url: string | null;
  read_title: string;
  read_author: string;
  read_error: string;
  status: ScanStatus;
  confidence: number;
  match_id: string;
  candidates: Candidate[];
  resolved: boolean;
};

export type Scan = {
  id: number;
  created_at: string;
  error: string;
  timings: {
    detect_ms: number | null;
    vlm_ms: number | null;
    match_ms: number | null;
    total_ms: number | null;
    vlm_input_tokens: number | null;
    vlm_output_tokens: number | null;
  };
  counts: Record<ScanStatus, number>;
  items: ScanItem[];
};

export type LibraryBook = {
  id: number;
  catalog_id: string;
  title: string;
  author: string;
  added_at: string;
  manually_entered: boolean;
};

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      `Could not reach the server at ${BASE_URL}. Is it running?`
    );
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // Keep the status-based message.
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Absolute URL for a crop, which the API may return relative. */
export function mediaUrl(url: string | null): string | undefined {
  if (!url) return undefined;
  return url.startsWith('http') ? url : `${BASE_URL}${url}`;
}

export async function uploadScan(uri: string, fileName = 'shelf.jpg'): Promise<Scan> {
  const form = new FormData();

  if (uri.startsWith('data:') || uri.startsWith('blob:')) {
    // Web: the picker hands back a blob URL that fetch can read.
    const blob = await (await fetch(uri)).blob();
    form.append('image', blob, fileName);
  } else {
    // Native: React Native's FormData takes a file descriptor object.
    const match = /\.(\w+)$/.exec(uri);
    const extension = (match?.[1] ?? 'jpg').toLowerCase();
    form.append('image', {
      uri,
      name: fileName,
      type: extension === 'png' ? 'image/png' : 'image/jpeg',
    } as unknown as Blob);
  }

  return request<Scan>('/api/scans/', { method: 'POST', body: form });
}

export const getScan = (id: number | string) => request<Scan>(`/api/scans/${id}/`);

export const getLibrary = () => request<LibraryBook[]>('/api/library/');

export const removeBook = (id: number) =>
  request<void>(`/api/library/${id}/`, { method: 'DELETE' });

export const searchCatalog = (q: string) =>
  request<{ results: Candidate[] }>(`/api/catalog/search/?q=${encodeURIComponent(q)}`);

export type ResolveResult = {
  resolved: boolean;
  already_in_library?: boolean;
  book: LibraryBook | null;
};

export function resolveItem(
  itemId: number,
  action: 'confirm' | 'correct' | 'discard',
  payload: { catalog_id?: string; title?: string; author?: string } = {}
) {
  return request<ResolveResult>(`/api/items/${itemId}/resolve/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, ...payload }),
  });
}

export { BASE_URL };
