/**
 * TypeScript mirrors of the backend's response schemas.
 * Keeping these in one file means the whole app shares one source of truth
 * for API shapes — a field rename surfaces as a compile error, not a runtime
 * surprise.
 */

export type UserRole = "admin" | "manager" | "employee";

export type MeetingStatus =
  | "uploaded"
  | "extracting"
  | "transcribing"
  | "diarizing"
  | "analyzing"
  | "embedding"
  | "completed"
  | "failed";

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  meta: PaginationMeta | null;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  organization_id: string;
  is_active: boolean;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface MeetingFile {
  id: string;
  file_type: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
}

export interface Meeting {
  id: string;
  title: string;
  description: string | null;
  status: MeetingStatus;
  meeting_date: string | null;
  duration_seconds: number | null;
  tags: string[];
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface MeetingDetail extends Meeting {
  files: MeetingFile[];
}

export interface TranscriptSegment {
  id: string;
  segment_index: number;
  text: string;
  start_time: number;
  end_time: number;
  confidence: number | null;
  speaker_id: string | null;
  speaker_label: string | null;
}

export interface Transcript {
  meeting_id: string;
  status: MeetingStatus;
  duration_seconds: number | null;
  segment_count: number;
  segments: TranscriptSegment[];
}

export interface Speaker {
  id: string;
  diarization_label: string;
  display_name: string | null;
  label: string;
}

export interface Summary {
  summary_type: "full" | "executive";
  content: string;
  model_used: string;
}

export interface Insight {
  id: string;
  insight_type: string;
  content: string;
  timestamp_reference: number | null;
}

export interface ActionItem {
  id: string;
  description: string;
  assignee_name: string | null;
  assignee_user_id: string | null;
  due_date: string | null;
  priority: "low" | "medium" | "high";
  status: "open" | "in_progress" | "done";
  created_at: string;
}

export interface Intelligence {
  meeting_id: string;
  summaries: Summary[];
  insights: Insight[];
  action_items: ActionItem[];
}

export interface Citation {
  excerpt: number;
  meeting_id: string | null;
  chunk_index: number | null;
  start_time: number | null;
  end_time: number | null;
  score: number;
  text: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  meeting_id: string | null;
  created_at: string;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[];
}

export interface SearchResult {
  meeting_id: string | null;
  chunk_index: number | null;
  start_time: number | null;
  end_time: number | null;
  score: number;
  text: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
}
