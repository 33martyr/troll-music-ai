import type {
  Asset,
  BattleCharacter,
  BattleRequest,
  BeatRequest,
  Capability,
  Hardware,
  Job,
  LyricSection,
  LyricsAsset,
  LyricsRequest,
  Project,
  ProviderCheck,
  ProviderState,
  ProviderUpdate,
  StockVoices,
  StudioOptions,
  VoiceProfile,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

// Only needed when the backend sets TROLL_API_KEY. Kept in this browser only.
const KEY_STORAGE = "troll_api_key";
export const getApiKey = () => (typeof window === "undefined" ? "" : (window.localStorage.getItem(KEY_STORAGE) ?? ""));
export function setApiKey(key: string) {
  if (key) window.localStorage.setItem(KEY_STORAGE, key);
  else window.localStorage.removeItem(KEY_STORAGE);
}

export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
  ) {
    super(message);
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const headers: Record<string, string> = {};
  if (typeof init?.body === "string") headers["Content-Type"] = "application/json";
  const key = getApiKey();
  if (key) headers.Authorization = `Bearer ${key}`;
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(
      `Can't reach the backend at ${API_URL}. Start it with: python scripts/dev_backend.py`,
      "backend_unreachable",
      0,
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message =
      response.status === 401
        ? "The backend needs an API key. Enter it in Settings."
        : (body?.error?.message ?? `Request failed (${response.status}).`);
    throw new ApiError(message, body?.error?.code ?? "http_error", response.status);
  }
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  return response.status === 204 ? (undefined as T) : response.json();
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const put = <T>(path: string, body: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body) });
const patch = <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
const remove = <T = void>(path: string) => request<T>(path, { method: "DELETE" });

function form(fields: Record<string, string | number | boolean | File | null | undefined>): FormData {
  const data = new FormData();
  for (const [name, value] of Object.entries(fields)) {
    if (value === null || value === undefined || value === "") continue;
    data.append(name, value instanceof File ? value : String(value));
  }
  return data;
}

export interface VocalsBody {
  project_id?: string | null;
  lyrics_asset_id: string;
  beat_asset_id?: string | null;
  bpm?: number | null;
  voice?: string | null;
  voice_b?: string | null;
  voice_profile_id?: string | null;
}
export interface SongBody extends Omit<VocalsBody, "bpm"> {
  mode: "mix" | "model";
  vocals_asset_id?: string | null;
  title?: string | null;
  vocal_gain_db?: number;
  beat_gain_db?: number;
  style_prompt?: string | null;
  duration_seconds?: number | null;
}
export interface VideoBody {
  project_id?: string | null;
  audio_asset_id?: string | null;
  lyrics_asset_id?: string | null;
  title?: string | null;
  style: string;
  aspect: string;
  subtitles: boolean;
  duration_seconds?: number | null;
  notes?: string | null;
}
export interface ArtworkBody {
  project_id?: string | null;
  lyrics_asset_id?: string | null;
  title: string;
  genre: string;
  mood?: string | null;
  style: string;
  character?: string | null;
  notes?: string | null;
}

export const api = {
  health: () => request<{ status: string; auth_required: boolean }>("/api/health"),
  capabilities: () => request<Capability[]>("/api/system/capabilities"),
  providers: () => request<ProviderState[]>("/api/system/providers"),
  updateProvider: (kind: string, body: ProviderUpdate) => put<ProviderState>(`/api/system/providers/${kind}`, body),
  resetProvider: (kind: string) => remove<ProviderState>(`/api/system/providers/${kind}`),
  checkProvider: (kind: string) => post<ProviderCheck>(`/api/system/providers/${kind}/check`),
  hardware: () => request<Hardware>("/api/system/hardware"),
  options: () => request<StudioOptions>("/api/meta/options"),
  lyricsOptions: () => request<StudioOptions>("/api/meta/options"),

  projects: () => request<Project[]>("/api/projects"),
  project: (id: string) => request<Project>(`/api/projects/${id}`),
  createProject: (name: string, description = "") => post<Project>("/api/projects", { name, description }),
  updateProject: (id: string, body: { name?: string; description?: string }) => patch<Project>(`/api/projects/${id}`, body),
  deleteProject: (id: string) => remove(`/api/projects/${id}`),
  duplicateProject: (id: string) => post<Project>(`/api/projects/${id}/duplicate`),
  projectAssets: (id: string) => request<Asset[]>(`/api/projects/${id}/assets`),
  projectJobs: (id: string) => request<Job[]>(`/api/projects/${id}/jobs`),

  assets: (query: string) => request<Asset[]>(`/api/assets?${query}`),
  asset: <T = Record<string, unknown>>(id: string) => request<Asset<T>>(`/api/assets/${id}`),
  assetHistory: (id: string) => request<Asset[]>(`/api/assets/${id}/history`),
  assetSources: (id: string) => request<{ relation: string; asset: Asset }[]>(`/api/assets/${id}/sources`),
  updateAsset: (id: string, body: { approved?: boolean; project_id?: string | null; title?: string }) =>
    patch<Asset>(`/api/assets/${id}`, body),
  deleteAsset: (id: string) => remove(`/api/assets/${id}`),
  uploadAudio: (file: File, kind: string, projectId: string | null, bpm: number | null) =>
    request<Asset>("/api/assets/upload", { method: "POST", body: form({ file, kind, project_id: projectId, bpm }) }),

  jobs: (query = "") => request<Job[]>(`/api/jobs?${query}`),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => post<Job>(`/api/jobs/${id}/cancel`),
  retryJob: (id: string) => post<Job>(`/api/jobs/${id}/retry`),

  generateLyrics: (lyricsRequest: LyricsRequest, projectId: string | null) =>
    post<Job>("/api/lyrics/generate", { project_id: projectId, request: lyricsRequest }),
  importLyrics: (title: string, text: string, projectId: string | null) =>
    post<LyricsAsset>("/api/lyrics/import", { title, text, project_id: projectId }),
  regenerateSection: (assetId: string, sectionId: string, instruction?: string) =>
    post<Job>(`/api/lyrics/${assetId}/regenerate-section`, { section_id: sectionId, instruction }),
  rewriteLyrics: (assetId: string, body: { mode: string; instruction?: string; rhyme_scheme?: string }) =>
    post<Job>(`/api/lyrics/${assetId}/rewrite`, body),
  saveLyrics: (assetId: string, title: string, sections: LyricSection[]) =>
    put<LyricsAsset>(`/api/lyrics/${assetId}`, { title, sections }),

  generateBattle: (battle: BattleRequest, projectId: string | null) =>
    post<Job>("/api/battles/generate", { project_id: projectId, request: battle }),
  suggestCharacters: (topic: string) =>
    post<{ characters: BattleCharacter[]; provider: string; is_mock: boolean }>("/api/battles/characters", { topic }),

  generateBeat: (beat: BeatRequest, projectId: string | null, lyricsAssetId?: string | null) =>
    post<Job>("/api/beats/generate", { project_id: projectId, lyrics_asset_id: lyricsAssetId ?? null, request: beat }),
  generateVocals: (body: VocalsBody) => post<Job>("/api/vocals/generate", body),
  convertVocals: (sourceAssetId: string, voiceProfileId: string) =>
    post<Job>("/api/vocals/convert", { source_asset_id: sourceAssetId, voice_profile_id: voiceProfileId }),
  generateSong: (body: SongBody) => post<Job>("/api/songs/generate", body),
  generateVideo: (body: VideoBody) => post<Job>("/api/videos/generate", body),
  generateArtwork: (body: ArtworkBody) => post<Job>("/api/artwork/generate", body),

  voices: () => request<VoiceProfile[]>("/api/voices"),
  stockVoices: () => request<StockVoices>("/api/voices/stock"),
  createVoice: (fields: { name: string; owner_name: string; consent_statement: string; consent_confirmed: boolean; file: File }) =>
    request<VoiceProfile>("/api/voices", { method: "POST", body: form(fields) }),
  deleteVoice: (id: string) => remove<{ deleted: boolean; note: string }>(`/api/voices/${id}`),
};

/** URL a media element can load directly. Carries a signed token when the backend uses an API key. */
export function fileUrl(asset: Pick<Asset, "id" | "file_token">, asDownload = false): string {
  const query = new URLSearchParams();
  if (asset.file_token) query.set("token", asset.file_token);
  if (asDownload) query.set("download", "1");
  const suffix = query.toString();
  return `${API_URL}/api/assets/${asset.id}/file${suffix ? `?${suffix}` : ""}`;
}

export function voiceSampleUrl(profile: VoiceProfile): string {
  return `${API_URL}/api/voices/${profile.id}/sample${profile.sample_token ? `?token=${profile.sample_token}` : ""}`;
}

export const isActive = (job: Job | null) => job?.status === "queued" || job?.status === "processing";

/** Poll a job until it finishes. Resolves with the finished job, rejects if it failed or was cancelled. */
export async function waitForJob(job: Job, onUpdate: (job: Job) => void): Promise<Job> {
  let current = job;
  onUpdate(current);
  while (isActive(current)) {
    await new Promise((resolve) => setTimeout(resolve, 700));
    current = await api.job(current.id);
    onUpdate(current);
  }
  if (current.status === "cancelled") throw new ApiError("Cancelled.", "cancelled", 0);
  if (current.status === "failed") {
    throw new ApiError(current.error ?? "Generation failed.", current.error_code ?? "job_failed", 0);
  }
  return current;
}

/** Fetch a file from the API and hand it to the browser as a download. */
export async function download(path: string, fallbackName: string): Promise<void> {
  const response = await send(path);
  const match = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = match?.[1] ?? fallbackName;
  link.click();
  URL.revokeObjectURL(url);
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}
