"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import type { AuditEventProjection } from "@/lib/audit";
import { useApiErrorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import type { Page } from "@/lib/records";

const LIMIT = 20;

type LoadState =
  | { status: "loading" }
  | { status: "notFound" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      items: AuditEventProjection[];
      nextCursor: string | null;
      loadingMore: boolean;
      loadMoreError: string | null;
    };

// This is the Patient's filtered projection only — an identifier, a
// clinician name, a provider, a coarse action, and which entry type was
// touched. Never clinical content (.claude/rules/clinical-safety.md).
export default function AuditEventsPage() {
  const t = useTranslations("audit");
  const tTimeline = useTranslations("timeline");
  const errorMessage = useApiErrorMessage();
  const router = useRouter();

  const [patientId, setPatientId] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    api
      .get<{ id: string }>("/patients/me")
      .then((profile) => {
        if (active) setPatientId(profile.id);
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && (err.status === 401 || err.code === "SESSION_EXPIRED")) {
          router.replace("/login");
          return;
        }
        if (err instanceof ApiError && err.status === 404) {
          setState({ status: "notFound" });
          return;
        }
        setState({ status: "error", message: errorMessage(err) });
      });
    return () => {
      active = false;
    };
    // errorMessage / router are stable for the page lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    Promise.resolve().then(() => {
      if (active) setState({ status: "loading" });
    });
    api
      .get<Page<AuditEventProjection>>(`/audit-events?patientId=${patientId}&limit=${LIMIT}`)
      .then((page) => {
        if (!active) return;
        setState({
          status: "ready",
          items: page.items,
          nextCursor: page.nextCursor,
          loadingMore: false,
          loadMoreError: null,
        });
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && (err.status === 401 || err.code === "SESSION_EXPIRED")) {
          router.replace("/login");
          return;
        }
        setState({ status: "error", message: errorMessage(err) });
      });
    return () => {
      active = false;
    };
    // errorMessage / router are stable for the page lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId, retryToken]);

  function loadMore() {
    if (!patientId || state.status !== "ready" || !state.nextCursor) return;
    const cursor = state.nextCursor;
    setState({ ...state, loadingMore: true, loadMoreError: null });
    api
      .get<Page<AuditEventProjection>>(
        `/audit-events?patientId=${patientId}&limit=${LIMIT}&cursor=${cursor}`,
      )
      .then((page) => {
        setState((prev) =>
          prev.status === "ready"
            ? {
                status: "ready",
                items: [...prev.items, ...page.items],
                nextCursor: page.nextCursor,
                loadingMore: false,
                loadMoreError: null,
              }
            : prev,
        );
      })
      .catch((err) => {
        setState((prev) =>
          prev.status === "ready"
            ? { ...prev, loadingMore: false, loadMoreError: errorMessage(err) }
            : prev,
        );
      });
  }

  function actionLabel(action: string): string {
    const key = `actions.${action}`;
    return t.has(key) ? t(key) : action;
  }

  function entryTypeLabel(entryType: string | null): string {
    if (!entryType) return t("entryTypeNone");
    return tTimeline.has(`entryTypes.${entryType}`) ? tTimeline(`entryTypes.${entryType}`) : entryType;
  }

  return (
    <section className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </div>

      {state.status === "loading" && <p className="text-sm text-muted">{t("loading")}</p>}

      {state.status === "notFound" && (
        <Callout tone="info" iconLabel={t("title")}>
          {t("notFound")}
        </Callout>
      )}

      {state.status === "error" && (
        <div className="space-y-3">
          <Callout tone="error" iconLabel={t("error.title")}>
            {state.message}
          </Callout>
          {patientId && (
            <Button variant="secondary" onClick={() => setRetryToken((n) => n + 1)}>
              {t("error.retry")}
            </Button>
          )}
        </div>
      )}

      {state.status === "ready" && state.items.length === 0 && (
        <Callout tone="info" iconLabel={t("empty.title")}>
          <span className="block font-medium text-foreground">{t("empty.title")}</span>
          <span>{t("empty.body")}</span>
        </Callout>
      )}

      {state.status === "ready" && state.items.length > 0 && (
        <div className="space-y-4">
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border bg-surface-raised text-xs text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">{t("fields.actor")}</th>
                  <th className="px-4 py-2 font-medium">{t("fields.provider")}</th>
                  <th className="px-4 py-2 font-medium">{t("fields.action")}</th>
                  <th className="px-4 py-2 font-medium">{t("fields.entryType")}</th>
                  <th className="px-4 py-2 font-medium">{t("fields.occurredAt")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border bg-surface">
                {state.items.map((event) => (
                  <tr key={event.id}>
                    <td className="px-4 py-2 text-foreground">{event.actorName}</td>
                    <td className="px-4 py-2 text-foreground">{event.providerName ?? t("entryTypeNone")}</td>
                    <td className="px-4 py-2 text-foreground">{actionLabel(event.action)}</td>
                    <td className="px-4 py-2 text-foreground">{entryTypeLabel(event.entryType)}</td>
                    <td className="px-4 py-2 tabular-nums text-foreground">
                      {formatDate(event.occurredAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {state.loadMoreError && (
            <Callout tone="error" iconLabel={t("error.title")}>
              {state.loadMoreError}
            </Callout>
          )}

          {state.nextCursor && (
            <Button
              variant="secondary"
              loading={state.loadingMore}
              onClick={loadMore}
              className="w-full sm:w-auto"
            >
              {state.loadingMore ? t("loadingMore") : t("loadMore")}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
