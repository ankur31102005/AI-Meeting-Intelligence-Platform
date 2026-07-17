/**
 * File upload with progress.
 *
 * fetch() can't report upload progress, so uploads use XMLHttpRequest — the
 * one place we bypass the fetch client. Auth + error-envelope handling are
 * replicated here to keep the same contract. (A 401 here is rare because the
 * user just loaded an authed page; we surface it rather than silently
 * refreshing mid-upload.)
 */

import { tokenStore } from "./api";
import type { ApiResponse, MeetingDetail } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export function uploadMeeting(
  file: File,
  title: string | undefined,
  onProgress: (percent: number) => void
): Promise<MeetingDetail> {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append("file", file);
    if (title) fd.append("title", title);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/meetings`);
    if (tokenStore.access) {
      xhr.setRequestHeader("Authorization", `Bearer ${tokenStore.access}`);
    }

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };

    xhr.onload = () => {
      let body: (ApiResponse<MeetingDetail> & { error?: { message: string } }) | null = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* fall through to generic error */
      }
      if (xhr.status >= 200 && xhr.status < 300 && body?.success && body.data) {
        resolve(body.data);
      } else {
        reject(new Error(body?.error?.message ?? `Upload failed (${xhr.status})`));
      }
    };

    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(fd);
  });
}

const ACCEPTED = [".mp3", ".wav", ".mp4"];

export function isAcceptedFile(name: string): boolean {
  return ACCEPTED.some((ext) => name.toLowerCase().endsWith(ext));
}

export const ACCEPTED_EXTENSIONS = ACCEPTED;
