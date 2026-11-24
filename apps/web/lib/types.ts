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
  intro_card?: boolean;
  meme_overlay?: boolean;
  format?: string;
  theme?: string;
  parody?: boolean;
  award?: string;
  background_provider?: string | null;
  troll?: TrollMeta;
}

// ---------------------------------- troll ---------------------------------- //

export type TrollKind = "diss_track" | "roast" | "rap_battle" | "meme_song" | "group_roast" | "funny_beat" | "meme_video";
export type Intensity = "friendly" | "savage" | "brutal" | "nuclear";

export interface TrollRequest {
  situation: string;
  kind: TrollKind;
  style: string;
  intensity: Intensity;
  delivery: string;
  target?: string | null;
  names?: string[];
  rapper_name?: string | null;
  explicit?: boolean;
  language?: string;
  template?: string | null;
  subgenre?: string | null;
  length?: string;
  instructions?: string | null;
  inside_jokes?: string[];
  people?: Participant[];
  group_name?: string | null;
  voice?: string | null;
  voice_b?: string | null;
}

export interface Participant {
  name: string;
  nickname?: string | null;
  description?: string | null;
  voice?: string | null;
}

export interface RoastTemplate {
  id: string;
  name: string;
  emoji: string;
  scenario: string;
  kind: TrollKind;
  style: string;
  intensity: Intensity;
  delivery: string;
  guidance: string;
  examples: string[];
}

export interface PunchlineOptions {
  current: string | null;
  options: string[];
  provider: string;
  model: string | null;
  is_mock: boolean;
}

/** Stored on the song (or beat) a troll job made: where everything else is. */
export interface TrollMeta {
  kind: TrollKind;
  label: string;
  artist: string;
  target: string;
  style: string;
  intensity: Intensity;
  lyrics_asset_id: string | null;
  cover_asset_id: string | null;
  video_asset_id: string | null;
  warnings: string[];
  lyrics_reused?: boolean;
  remix_of?: string | null;
  request?: TrollRequest;
  with_video?: boolean;
  with_cover?: boolean;
}

export interface TrollOptions {
  kinds: { id: TrollKind; label: string }[];
  styles: { id: string; label: string; song: boolean }[];
  intensities: { id: Intensity; label: string }[];
  deliveries: { id: string; label: string }[];
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

// --------------------------------- battles --------------------------------- //

export interface BattleScore {
  punchlines: number;
  flow: number;
  creativity: number;
  humor: number;
  entertainment: number;
  comment: string;
}

/** The AI judges' opinion of a battle. Not a measurement. */
export interface Scorecard {
  scores: Record<string, BattleScore>;
  winner: string | null;
  announcement: string;
  best_line: string | null;
  overall: Record<string, number>;
}

export interface VoteTally {
  counts: Record<string, number>;
  total: number;
  your_vote: string | null;
}

export interface BattleInfo {
  battle_id: string;
  rappers: [string, string];
  lyrics: Asset<Lyrics>;
  scorecard: Asset<Scorecard> | null;
  votes: VoteTally;
}

export type FactoryItem =
  | "vertical_video"
  | "square_video"
  | "wide_video"
  | "square_cover"
  | "concert_poster"
  | "award_card"
  | "streaming_card"
  | "reaction_meme";

// ------------------------------ Troll Universe ----------------------------- //

export interface RapperStats {
  punchline: number;
  flow: number;
  comedy: number;
  creativity: number;
  reputation: number;
}

/** A fictional rapper. Private to this installation. */
export interface Rapper {
  id: string;
  name: string;
  personality: string;
  style: string;
  delivery: string;
  catchphrase: string;
  bio: string;
  stats: RapperStats;
  overall: number;
  voice: string | null;
  avatar: Asset | null;
  card: Asset | null;
  wins: number;
  losses: number;
  draws: number;
  titles: string[];
  origin: string;
  provider: string | null;
  model: string | null;
  is_mock: boolean;
}

export interface RivalryHistoryItem {
  track: Asset;
  kind: TrollKind;
  settled: boolean;
  winner_id: string | null;
  source: "votes" | "judges" | "manual" | null;
}

export interface Rivalry {
  id: string;
  tagline: string;
  project_id: string | null;
  rapper_a: Rapper;
  rapper_b: Rapper;
  record: { a: number; b: number; draws: number };
  champion_id: string | null;
  champion_wins_needed: number;
  history: RivalryHistoryItem[];
}
