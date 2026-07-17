/**
 * Domain API functions — one thin async per backend endpoint.
 * Components call these (never fetch directly), so the wire format lives in
 * exactly one layer.
 */

import { api } from "./api";
import type {
  ApiResponse,
  ChatMessage,
  ChatSession,
  ChatSessionDetail,
  Intelligence,
  Meeting,
  MeetingDetail,
  SearchResponse,
  Speaker,
  TokenPair,
  Transcript,
  User,
} from "./types";

// --- Auth ---
export const authApi = {
  login: (email: string, password: string) =>
    api.request<TokenPair>("/auth/login", { method: "POST", body: { email, password }, auth: false }),
  signup: (body: {
    email: string;
    password: string;
    full_name: string;
    organization_name: string;
  }) => api.request<User>("/auth/signup", { method: "POST", body, auth: false }),
  me: () => api.request<User>("/auth/me"),
  logout: (refresh_token: string) =>
    api.request<{ message: string }>("/auth/logout", {
      method: "POST",
      body: { refresh_token },
    }),
};

// --- Meetings ---
export const meetingsApi = {
  list: (params: { page?: number; page_size?: number; search?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.page) q.set("page", String(params.page));
    if (params.page_size) q.set("page_size", String(params.page_size));
    if (params.search) q.set("search", params.search);
    return api.requestWithMeta<Meeting[]>(`/meetings?${q.toString()}`);
  },
  get: (id: string) => api.request<MeetingDetail>(`/meetings/${id}`),
  status: (id: string) =>
    api.request<{ status: string; error_message: string | null }>(`/meetings/${id}/status`),
  transcript: (id: string) => api.request<Transcript>(`/meetings/${id}/transcript`),
  speakers: (id: string) => api.request<Speaker[]>(`/meetings/${id}/speakers`),
  renameSpeaker: (mid: string, sid: string, display_name: string) =>
    api.request<Speaker>(`/meetings/${mid}/speakers/${sid}`, {
      method: "PATCH",
      body: { display_name },
    }),
  intelligence: (id: string) => api.request<Intelligence>(`/meetings/${id}/intelligence`),
  updateActionItem: (
    mid: string,
    itemId: string,
    body: { status?: string; priority?: string; description?: string }
  ) =>
    api.request(`/meetings/${mid}/action-items/${itemId}`, { method: "PATCH", body }),
  update: (id: string, body: { title?: string; description?: string; tags?: string[] }) =>
    api.request<Meeting>(`/meetings/${id}`, { method: "PATCH", body }),
  remove: (id: string) => api.request(`/meetings/${id}`, { method: "DELETE" }),
  reprocess: (id: string) => api.request(`/meetings/${id}/reprocess`, { method: "POST" }),
  upload: (file: File, title?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (title) fd.append("title", title);
    return api.request<MeetingDetail>("/meetings", { method: "POST", formData: fd });
  },
};

// --- Chat & Search ---
export const chatApi = {
  search: (query: string, meeting_id?: string, top_k = 5) =>
    api.request<SearchResponse>("/search", {
      method: "POST",
      body: { query, meeting_id, top_k },
    }),
  createSession: (meeting_id?: string, title?: string) =>
    api.request<ChatSession>("/chat/sessions", { method: "POST", body: { meeting_id, title } }),
  listSessions: () => api.request<ChatSession[]>("/chat/sessions"),
  getSession: (id: string) => api.request<ChatSessionDetail>(`/chat/sessions/${id}`),
  ask: (sessionId: string, question: string) =>
    api.request<ChatMessage>(`/chat/sessions/${sessionId}/messages`, {
      method: "POST",
      body: { question },
    }),
};

export type { ApiResponse };
