import { ApiError, type ApiErrorBody } from "./api";
import type { Document as RecordDocument, Page_EntrySummary_ } from "./generated/api";
export { EntryTypeValues as ENTRY_TYPES } from "./generated/api";
export type { EntryType, EntryCreate, EntrySummary, EntryDetail, Document as RecordDocument } from "./generated/api";
export type Page<T> = Omit<Page_EntrySummary_, "items"> & { items: T[] };

/** The three MIME types the upload endpoint accepts and the viewer renders
 * (backend `service._MAGIC`, docs/api-conventions.md: MIME allowlist). */
export const VIEWABLE_DOCUMENT_MIME_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
] as const;

/**
 * Upload a document to an Entry via `XMLHttpRequest` rather than `fetch` —
 * only `XMLHttpRequest` exposes upload progress events, and the upload UI
 * needs a progress bar (issue #34). `onProgress` receives a 0..1 fraction.
 *
 * A 413 is handled explicitly even when the rejecting layer (Caddy's outer
 * body limit, P2.11) sends no JSON envelope at all: the status code alone is
 * enough to synthesize `PAYLOAD_TOO_LARGE` so the caller always gets the
 * specific "too large" message, never a generic failure.
 */
export function uploadDocument(
  patientId: string,
  entryId: string,
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<RecordDocument> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(
      "POST",
      `/api/v1/patients/${patientId}/entries/${entryId}/documents`,
    );
    xhr.withCredentials = true;

    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) {
        onProgress(event.loaded / event.total);
      }
    };

    xhr.onerror = () => {
      reject(new ApiError(0, { code: "NETWORK", message: "Network error" }));
    };

    xhr.onload = () => {
      let payload: unknown;
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
      } catch {
        payload = undefined;
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as RecordDocument);
        return;
      }

      const envelope = (payload as { error?: ApiErrorBody } | undefined)?.error;
      reject(
        new ApiError(
          xhr.status,
          envelope ?? {
            code: xhr.status === 413 ? "PAYLOAD_TOO_LARGE" : "GENERIC",
            message: `HTTP ${xhr.status}`,
          },
        ),
      );
    };

    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
