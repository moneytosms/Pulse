"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { ClinicalText } from "@/components/ClinicalText";
import { TriangleAlertIcon } from "lucide-react";
import { ApiError } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/errors";
import { VIEWABLE_DOCUMENT_MIME_TYPES, type RecordDocument } from "@/lib/records";

type ViewerState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; url: string };

/**
 * Fetches a doc's bytes as a blob and renders it inline — the serve
 * route sends `Content-Disposition: attachment` (backend/records/routes.py),
 * so a plain link would force a download rather than preview. Only the three
 * MIME types the upload endpoint accepts get an inline preview; anything
 * else states plainly that no preview is available (issue #34).
 */
export function DocumentViewer({ doc }: { doc: RecordDocument }) {
  const t = useTranslations("timeline");
  const errorMessage = useApiErrorMessage();
  const [state, setState] = useState<ViewerState>({ status: "idle" });

  // Release the object URL when it is replaced or the component unmounts.
  useEffect(() => {
    if (state.status !== "ready") return;
    const { url } = state;
    return () => URL.revokeObjectURL(url);
  }, [state]);

  const viewable = (VIEWABLE_DOCUMENT_MIME_TYPES as readonly string[]).includes(
    doc.mimeType,
  );

  async function load() {
    setState({ status: "loading" });
    try {
      const response = await fetch(`/api/v1/documents/${doc.id}`, {
        credentials: "include",
      });
      if (!response.ok) {
        const isJson = response.headers
          .get("content-type")
          ?.toLowerCase()
          .includes("application/json");
        const payload = isJson ? await response.json().catch(() => undefined) : undefined;
        const envelope = payload?.error;
        throw new ApiError(
          response.status,
          envelope ?? { code: "GENERIC", message: `HTTP ${response.status}` },
        );
      }
      const blob = await response.blob();
      setState({ status: "ready", url: URL.createObjectURL(blob) });
    } catch (err) {
      setState({ status: "error", message: errorMessage(err) });
    }
  }

  return (
    <li className="space-y-2 rounded-xl border bg-card px-4 py-3 text-sm shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <ClinicalText>{doc.filename}</ClinicalText>
        {viewable && state.status !== "ready" && (
          <Button
            variant="outline"
            className="shrink-0"
            disabled={state.status === "loading"}
            aria-busy={state.status === "loading"}
            onClick={load}
          >
            {state.status === "loading" && <Spinner />}
            {t("detail.documentViewer.view")}
          </Button>
        )}
      </div>

      {!viewable && (
        <p className="text-xs text-muted-foreground">{t("detail.documentViewer.unsupported")}</p>
      )}

      {state.status === "error" && (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>{t("error.title")}</AlertTitle>
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      )}

      {state.status === "ready" && doc.mimeType === "application/pdf" && (
        <iframe
          src={state.url}
          title={doc.filename}
          className="h-96 w-full rounded-md border bg-background"
        />
      )}

      {state.status === "ready" && doc.mimeType !== "application/pdf" && (
        // eslint-disable-next-line @next/next/no-img-element -- blob: URL, not an optimizable remote asset
        <img
          src={state.url}
          alt={doc.filename}
          className="max-h-96 w-full rounded-md border object-contain"
        />
      )}
    </li>
  );
}
