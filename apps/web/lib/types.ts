// Mirrors the backend's response models (backend/models/schemas.py).

export type SectionType = "intro" | "verse" | "chorus" | "bridge" | "outro";

export interface LyricSection {
  id: string;
  type: SectionType;
  label: string;
  lines: string[];
  performer?: string | null;
}

export interface Lyrics {
  title: string;
  sections: LyricSection[];
  suggested_bpm: number | null;
  suggested_genre: string | null;
  beat_notes: string[];
  language: string;
  explicit: boolean;
}

export interface LyricsRequest {
  prompt: string;
  genre: string;
  mood: string;
  language: string;
  style: string;
  troll_intensity: number;
  explicit: boolean;
  length: string;
  verses: number;
  chorus_style: string;
  rhyme_complexity: string;
  include_bridge: boolean;
  persona: string | null;
}

export interface LineTiming {
  section_id: string;
  label: string;
  performer: string | null;
  text: string;
  start: number;
  end: number;
}

/** Facts about a media file. Which keys are present depends on the asset kind. */
export interface AssetMeta {
  bpm?: number | null;
  bpm_exact?: boolean;
  genre?: string;
  mood?: string | null;
  key?: string | null;
  looped?: boolean;
  delivery?: "spoken" | "sung" | null;
  voice?: string | null;
  line_timings?: LineTiming[] | null;
  mode?: string;
  width?: number;
  height?: number;
  aspect?: string;
  style?: string;
  scenes?: number;
  subtitles?: boolean;
  has_audio?: boolean;
  renderer?: string;
  image_provider?: string | null;
  image_fallbacks?: number;
  storyboard_source?: string;
  storyboard_asset_id?: string;
  original_filename?: string;
}

export interface Asset<TContent = Record<string, unknown>> {
  id: string;
  project_id: string | null;
  kind: string;
  title: string;
  content: TContent | null;
  params: Record<string, unknown> | null;
  meta: AssetMeta | null;
  mime_type: string | null;
  size_bytes: number | null;
  duration_seconds: number | null;
  provider: string | null;
  model: string | null;
  is_mock: boolean;
  /** False for built-in engines and uploads: real output, not from an AI model. */
  is_ai: boolean;
  origin: string;
  parent_id: string | null;
  root_id: string;
  version: number;
  is_latest: boolean;
  approved: boolean;
  created_at: string;
  has_file: boolean;
  file_token: string | null;
}

export type LyricsAsset = Asset<Lyrics>;

export interface StoryboardScene {
  index: number;
  start: number;
  end: number;
  label: string;
  lines: string[];
  description: string;
  image_prompt: string;
}
export interface Storyboard {
  title: string;
  style: string;
  aspect: string;
  duration: number;
  source: "llm" | "template";
  scenes: StoryboardScene[];
}

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  asset_counts: Record<string, number>;
}

export type JobStatus = "queued" | "processing" | "completed" | "failed" | "cancelled";

export interface Job {
  id: string;
  project_id: string | null;
  kind: string;
  status: JobStatus;
  progress: number;
  stage: string;
  provider: string | null;
  model: string | null;
  result_asset_id: string | null;
  result_asset_ids: string[];
  retry_of: string | null;
  error_code: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Capability {
  kind: string;
  label: string;
  implemented: boolean;
  configured: boolean;
  provider: string | null;
  model: string | null;
  endpoint: string | null;
  is_mock: boolean;
  is_ai: boolean;
  note: string;
}

export interface ProviderCheck {
  ok: boolean;
  detail: string;
  models: string[];
}

export interface ProviderOption {
  name: string;
  label: string;
  description: string;
  local: boolean;
  is_ai: boolean;
  is_mock: boolean;
  needs_api_key: boolean;
  needs_base_url: boolean;
  needs_model: boolean;
  default_base_url: string | null;
  default_model: string | null;
  suggested_models: string[];
  capabilities: string[];
  params: string[];
  hardware: string;
  license: string;
  commercial_use: boolean | null;
  setup: string;
  /** False = the adapter is written but has not been run against the real service. */
  verified: boolean;
  missing_packages: string[];
}

export interface ProviderState {
  kind: string;
  label: string;
  source: "environment" | "settings" | "override";
  provider: string;
  model: string | null;
  base_url: string | null;
  has_api_key: boolean;
  enabled: boolean;
  configured: boolean;
  error: string;
  is_ai: boolean;
  is_mock: boolean;
  options: ProviderOption[];
}

export interface ProviderUpdate {
  provider: string;
  model?: string | null;
  base_url?: string | null;
  api_key?: string | null;
  enabled: boolean;
}

export interface Hardware {
  platform: string;
  python: string;
  ffmpeg: { ok: boolean; detail: string };
  gpus: { name: string; memory_total_mb: number; memory_used_mb: number | null }[];
  packages: Record<string, boolean>;
}

export interface VoiceProfile {
  id: string;
  name: string;
  owner_name: string;
  consent_statement: string;
  consent_given_at: string;
  provider: string | null;
  meta: { duration_seconds?: number; warnings?: string[] } | null;
  created_at: string;
  usable: boolean;
  sample_token: string | null;
}

export interface StockVoices {
  provider: string | null;
  model: string | null;
  is_ai: boolean;
  voices: string[];
  speech: boolean;
  singing: boolean;
  cloning: boolean;
  conversion: boolean;
  note: string;
}

export interface StudioOptions {
  styles: string[];
  genres: string[];
  moods: string[];
  lengths: string[];
  chorus_styles: string[];
  rhyme_complexities: string[];
  rhyme_schemes: string[];
  rewrite_modes: string[];
  instruments: string[];
  visual_styles: string[];
  aspects: string[];
  max_upload_mb: number;
}
export type LyricsOptions = StudioOptions;

export interface BeatRequest {
  genre: string;
  bpm: number | null;
  mood: string | null;
  instruments: string[];
  energy: number;
  duration_seconds: number;
  key: string | null;
  description: string | null;
  variations: number;
}

export interface BattleCharacter {
  name: string;
  personality: string;
  style: string;
}
export interface BattleRequest {
  topic: string;
  character_a: BattleCharacter;
  character_b: BattleCharacter;
  rounds: number;
  genre: string;
  language: string;
  troll_intensity: number;
  explicit: boolean;
}
