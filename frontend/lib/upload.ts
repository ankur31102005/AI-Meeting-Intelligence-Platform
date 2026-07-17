/**
 * File upload with progress.
 *
 * fetch() can't report upload progress, so uploads use XMLHttpRequest — the
 * one place we bypass the fetch client. It reuses the fetch client's token
 * refresh (tryRefresh): if the access token has expired, a 401 triggers ONE
 * refresh + retry, exactly like every other request — so a user who left the
 * page open past the token lifetime can still upload.
 */

import { tryRefresh, tokenStore } from "./api";
import type { ApiResponse, MeetingDetail } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

/** One XHR attempt. Resolves the meeting, or rejects with {status, message}. */
function attempt(
  fd: FormData,
  onProgress: (percent: number) => void
): Promise<MeetingDetail> {
  return new Promise((resolve, reject) => {
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
        reject(
          Object.assign(
            new Error(body?.error?.message ?? `Upload failed (${xhr.status})`),
            { status: xhr.status }
          )
        );
      }
    };

    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(fd);
  });
}

export async function uploadMeeting(
  file: File,
  title: string | undefined,
  onProgress: (percent: number) => void
): Promise<MeetingDetail> {
  const buildForm = () => {
    const fd = new FormData();
    fd.append("file", file);
    if (title) fd.append("title", title);
    return fd;
  };

  try {
    return await attempt(buildForm(), onProgress);
  } catch (err) {
    // Expired access token -> refresh once and retry the whole upload.
    if ((err as { status?: number }).status === 401 && (await tryRefresh())) {
      onProgress(0);
      return attempt(buildForm(), onProgress);
    }
    throw err;
  }
}

const ACCEPTED = [".mp3", ".wav", ".mp4"];

export function isAcceptedFile(name: string): boolean {
  return ACCEPTED.some((ext) => name.toLowerCase().endsWith(ext));
}

export const ACCEPTED_EXTENSIONS = ACCEPTED;
