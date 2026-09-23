"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ActivityIcon, CircleAlertIcon, InfoIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import type { AuditEventProjection } from "@/lib/audit";
import { useApiErrorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import type { Page } from "@/lib/records";

const LIMIT = 20;
const BREAK_GLASS_ACTION = "BREAK_GLASS_ACCESS";

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

// Severity badge is derived from `action`: BREAK_GLASS_ACCESS is the one
// action severe enough to warrant its own highlight and token set
// (.claude/rules/clinical-safety.md — break-glass is CRITICAL-audited).
// Everything else reads as a normal access.
function SeverityBadge({ isBreakGlass, label }: { isBreakGlass: boolean; label: string }) {
  return (
    <Badge
      variant="outline"
      className={
        isBreakGlass
          ? "border-break-glass bg-break-glass-surface text-break-glass"
          : "border-audit-normal bg-audit-normal-surface text-audit-normal"
      }
    >
      {isBreakGlass ? <CircleAlertIcon className="size-3.5" /> : <InfoIcon className="size-3.5" />}
      {label}
    </Badge>
  );
}

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
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 motion-reduce:animate-none space-y-8 duration-300">
      <div className="space-y-1">
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-pretty text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      {state.status === "loading" && (
        <div className="space-y-3" aria-hidden="true">
          <span className="sr-only">{t("loading")}</span>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 w-full rounded-xl" />
          ))}
        </div>
      )}

      {state.status === "notFound" && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ActivityIcon />
            </EmptyMedia>
            <EmptyTitle>{t("notFound")}</EmptyTitle>
          </EmptyHeader>
        </Empty>
      )}

      {state.status === "error" && (
        <div className="space-y-3">
          <Alert variant="destructive">
            <AlertTitle>{t("error.title")}</AlertTitle>
            <AlertDescription>{state.message}</AlertDescription>
          </Alert>
          {patientId && (
            <Button variant="outline" onClick={() => setRetryToken((n) => n + 1)}>
              {t("error.retry")}
            </Button>
          )}
        </div>
      )}

      {state.status === "ready" && state.items.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ActivityIcon />
            </EmptyMedia>
            <EmptyTitle>{t("empty.title")}</EmptyTitle>
            <EmptyDescription>{t("empty.body")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}

      {state.status === "ready" && state.items.length > 0 && (
        <div className="space-y-4">
          {/* Table on desktop; rows stack as cards on mobile (max-sm:) — one
              DOM per event so e2e text assertions never hit a strict-mode
              duplicate. */}
          <div className="overflow-x-auto rounded-xl border shadow-sm max-sm:border-none max-sm:shadow-none">
            <Table className="max-sm:block">
              <TableHeader className="max-sm:hidden">
                <TableRow>
                  <TableHead>{t("fields.actor")}</TableHead>
                  <TableHead>{t("fields.provider")}</TableHead>
                  <TableHead>{t("fields.action")}</TableHead>
                  <TableHead>{t("fields.entryType")}</TableHead>
                  <TableHead>{t("fields.occurredAt")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody className="max-sm:block max-sm:space-y-3">
                {state.items.map((event) => {
                  const isBreakGlass = event.action === BREAK_GLASS_ACTION;
                  return (
                    <TableRow
                      key={event.id}
                      className={
                        "max-sm:block max-sm:space-y-2 max-sm:rounded-xl max-sm:border max-sm:px-4 max-sm:py-3 max-sm:shadow-sm " +
                        (isBreakGlass ? "bg-break-glass-surface" : "")
                      }
                    >
                      <TableCell className="text-foreground max-sm:flex max-sm:items-center max-sm:justify-between">
                        <span className="hidden text-xs text-muted-foreground max-sm:inline">
                          {t("fields.actor")}
                        </span>
                        {event.actorName}
                      </TableCell>
                      <TableCell className="text-foreground max-sm:flex max-sm:items-center max-sm:justify-between">
                        <span className="hidden text-xs text-muted-foreground max-sm:inline">
                          {t("fields.provider")}
                        </span>
                        {event.providerName ?? t("entryTypeNone")}
                      </TableCell>
                      <TableCell className="max-sm:flex max-sm:items-center max-sm:justify-between">
                        <span className="hidden text-xs text-muted-foreground max-sm:inline">
                          {t("fields.action")}
                        </span>
                        <SeverityBadge isBreakGlass={isBreakGlass} label={actionLabel(event.action)} />
                      </TableCell>
                      <TableCell className="text-foreground max-sm:flex max-sm:items-center max-sm:justify-between">
                        <span className="hidden text-xs text-muted-foreground max-sm:inline">
                          {t("fields.entryType")}
                        </span>
                        {entryTypeLabel(event.entryType)}
                      </TableCell>
                      <TableCell className="tabular-nums text-foreground max-sm:flex max-sm:items-center max-sm:justify-between">
                        <span className="hidden text-xs text-muted-foreground max-sm:inline">
                          {t("fields.occurredAt")}
                        </span>
                        {formatDate(event.occurredAt)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          {state.loadMoreError && (
            <Alert variant="destructive">
              <AlertTitle>{t("error.title")}</AlertTitle>
              <AlertDescription>{state.loadMoreError}</AlertDescription>
            </Alert>
          )}

          {state.nextCursor && (
            <Button
              variant="outline"
              disabled={state.loadingMore}
              aria-busy={state.loadingMore}
              onClick={loadMore}
              className="min-h-11 w-full sm:min-h-8 sm:w-auto"
            >
              {state.loadingMore && <Spinner />}
              {state.loadingMore ? t("loadingMore") : t("loadMore")}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
