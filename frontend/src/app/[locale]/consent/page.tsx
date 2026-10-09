"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  CircleCheckIcon,
  CircleXIcon,
  ClockIcon,
  ShieldCheckIcon,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import type { Consent, ConsentStatus, RevocationRequest } from "@/lib/consent";
import { useApiErrorMessage } from "@/lib/errors";
import { formatDate, formatDateTime } from "@/lib/format";
import type { Page } from "@/lib/records";

// Icon + label per status — colour never carries meaning alone
// (.claude/rules/frontend.md).
const STATUS_ICONS: Record<ConsentStatus, typeof CircleCheckIcon> = {
  ACTIVE: CircleCheckIcon,
  REVOKED: CircleXIcon,
  EXPIRED: ClockIcon,
};

const STATUS_CLASSES: Record<ConsentStatus, string> = {
  ACTIVE: "border-consent-active bg-consent-active-surface text-consent-active",
  REVOKED: "border-critical-border bg-critical-surface text-consent-revoked",
  EXPIRED: "border-border bg-consent-expired-surface text-consent-expired",
};

const LIMIT = 20;

type LoadState =
  | { status: "loading" }
  | { status: "notFound" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      items: Consent[];
      nextCursor: string | null;
      loadingMore: boolean;
      loadMoreError: string | null;
    };

function StatusBadge({ status }: { status: ConsentStatus }) {
  const t = useTranslations("consent");
  const Icon = STATUS_ICONS[status];
  return (
    <Badge variant="outline" className={STATUS_CLASSES[status]}>
      <Icon className="size-3.5" />
      {t(`list.status.${status}`)}
    </Badge>
  );
}

function ConsentRowLeadIcon({ status }: { status: ConsentStatus }) {
  return (
    <div
      className={
        "flex size-9 shrink-0 items-center justify-center rounded-md " +
        (status === "ACTIVE"
          ? "bg-primary/10 text-primary"
          : "bg-muted text-muted-foreground")
      }
    >
      <ShieldCheckIcon className="size-4" />
    </div>
  );
}

function scopeSummary(
  consent: Consent,
  t: ReturnType<typeof useTranslations<"consent">>,
  tTimeline: ReturnType<typeof useTranslations<"timeline">>,
): { types: string; window: string } {
  const types = consent.entryTypes?.length
    ? consent.entryTypes
        .map((type) => tTimeline(`entryTypes.${type}`))
        .join(", ")
    : t("list.scope.allTypes");

  const from = consent.fromDate ? formatDate(consent.fromDate) : null;
  const to = consent.toDate ? formatDate(consent.toDate) : null;
  const window =
    from && to
      ? t("list.scope.dateWindow", { from, to })
      : from
        ? t("list.scope.fromOnly", { from })
        : to
          ? t("list.scope.toOnly", { to })
          : t("list.scope.noWindow");

  return { types, window };
}

// Revoke is reachable in one click-to-reveal + one click-to-confirm, inline
// on this list — never a separate page — because withdrawing access must be
// the frictionless direction (.claude/rules/backend.md, ADR step-up
// asymmetry). Grant is a full page with several required fields.
function RevokeControl({
  consent,
  onRevoked,
}: {
  consent: Consent;
  onRevoked: (updated: Consent) => void;
}) {
  const t = useTranslations("consent");
  const errorMessage = useApiErrorMessage();
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!confirming) {
    return (
      <Button
        variant="outline"
        onClick={() => setConfirming(true)}
        className="min-h-11 shrink-0 sm:min-h-8"
      >
        {t("list.revoke.action")}
      </Button>
    );
  }

  async function confirmRevoke() {
    setSubmitting(true);
    setError(null);
    try {
      const payload: RevocationRequest = { reason: reason || null };
      const updated = await api.post<Consent>(
        `/consents/${consent.id}/revocation`,
        payload,
      );
      onRevoked(updated);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="w-full space-y-2 rounded-xl border bg-muted p-4 shadow-sm sm:w-72">
      <p className="text-sm font-medium text-foreground">
        {t("list.revoke.confirmTitle")}
      </p>
      <p className="text-xs text-muted-foreground">
        {t("list.revoke.confirmBody")}
      </p>
      <div className="space-y-1">
        <Label
          htmlFor={`revoke-reason-${consent.id}`}
          className="text-xs text-muted-foreground"
        >
          {t("list.revoke.reasonLabel")}
        </Label>
        <Input
          id={`revoke-reason-${consent.id}`}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertTitle>{t("list.revoke.action")}</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <div className="flex gap-2">
        <Button
          disabled={submitting}
          aria-busy={submitting}
          onClick={confirmRevoke}
          className="min-h-11 flex-1 sm:min-h-8"
        >
          {submitting && <Spinner />}
          {submitting ? t("list.revoke.revoking") : t("list.revoke.confirm")}
        </Button>
        <Button
          variant="outline"
          onClick={() => setConfirming(false)}
          disabled={submitting}
          className="min-h-11 flex-1 sm:min-h-8"
        >
          {t("list.revoke.cancel")}
        </Button>
      </div>
    </div>
  );
}

function ConsentRow({
  consent,
  onRevoked,
}: {
  consent: Consent;
  onRevoked: (updated: Consent) => void;
}) {
  const locale = useLocale();
  const t = useTranslations("consent");
  const tTimeline = useTranslations("timeline");
  const { types, window } = scopeSummary(consent, t, tTimeline);

  return (
    <li className="space-y-3 rounded-xl border bg-card px-4 py-3 shadow-sm transition-colors hover:bg-muted/50">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <ConsentRowLeadIcon status={consent.status} />
          <span className="text-sm font-medium text-foreground">
            {consent.granteeName ?? consent.granteeUserId}
          </span>
        </div>
        <StatusBadge status={consent.status} />
      </div>

      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted-foreground">
            {t("list.fields.purpose")}
          </dt>
          <dd className="text-foreground">
            {t(`list.purpose.${consent.purpose}`)}
            {consent.purpose === "OTHER" && consent.purposeText
              ? ` — ${consent.purposeText}`
              : ""}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">
            {t("list.fields.scope")}
          </dt>
          <dd className="text-foreground">
            {types}
            <span className="text-muted-foreground"> · {window}</span>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">
            {t("list.fields.granted")}
          </dt>
          <dd className="text-foreground">
            {formatDateTime(consent.grantedAt, `${locale}-IN`)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">
            {consent.status === "REVOKED"
              ? t("list.fields.revokedAt")
              : t("list.fields.expires")}
          </dt>
          <dd className="text-foreground">
            {consent.status === "REVOKED" && consent.revokedAt
              ? formatDateTime(consent.revokedAt, `${locale}-IN`)
              : formatDateTime(consent.expiresAt, `${locale}-IN`)}
          </dd>
        </div>
      </dl>

      {consent.status === "ACTIVE" && (
        <div className="flex justify-end">
          <RevokeControl consent={consent} onRevoked={onRevoked} />
        </div>
      )}
    </li>
  );
}

export default function ConsentListPage() {
  const t = useTranslations("consent");
  const errorMessage = useApiErrorMessage();
  const router = useRouter();

  const [view, setView] = useState<"active" | "history">("active");
  const [patientId, setPatientId] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const paginationRequest = useRef<AbortController | null>(null);
  const [revokedNotice, setRevokedNotice] = useState(false);

  useEffect(() => {
    if (patientId) return;
    let active = true;
    Promise.resolve().then(() => {
      if (active) setState({ status: "loading" });
    });
    api
      .get<{ id: string }>("/patients/me")
      .then((profile) => {
        if (active) setPatientId(profile.id);
      })
      .catch((err) => {
        if (!active) return;
        if (
          err instanceof ApiError &&
          (err.status === 401 || err.code === "SESSION_EXPIRED")
        ) {
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
  }, [patientId, retryToken]);

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    Promise.resolve().then(() => {
      if (active) setState({ status: "loading" });
    });
    api
      .get<Page<Consent>>(
        `/consents?patientId=${patientId}&limit=${LIMIT}&view=${view}`,
      )
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
        if (
          err instanceof ApiError &&
          (err.status === 401 || err.code === "SESSION_EXPIRED")
        ) {
          router.replace("/login");
          return;
        }
        setState({ status: "error", message: errorMessage(err) });
      });
    return () => {
      paginationRequest.current?.abort();
      active = false;
    };
    // errorMessage / router are stable for the page lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId, retryToken, view]);

  useEffect(() => {
    const refresh = () => setRetryToken((n) => n + 1);
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", onVisible);
    const nextExpiry =
      state.status === "ready" && view === "active"
        ? Math.min(
            ...state.items.map((item) => new Date(item.expiresAt).getTime()),
          )
        : Infinity;
    const timer = Number.isFinite(nextExpiry)
      ? window.setTimeout(
          refresh,
          Math.min(
            Math.max(nextExpiry - Date.now() + 100, 1000),
            2_147_483_647,
          ),
        )
      : undefined;
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", onVisible);
      window.clearTimeout(timer);
    };
  }, [state, view]);

  function loadMore() {
    if (!patientId || state.status !== "ready" || !state.nextCursor) return;
    const cursor = state.nextCursor;
    paginationRequest.current?.abort();
    const controller = new AbortController();
    paginationRequest.current = controller;
    setState({ ...state, loadingMore: true, loadMoreError: null });
    api
      .get<Page<Consent>>(
        `/consents?patientId=${patientId}&limit=${LIMIT}&view=${view}&cursor=${encodeURIComponent(cursor)}`,
        { signal: controller.signal },
      )
      .then((page) => {
        if (controller.signal.aborted) return;
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
        if (controller.signal.aborted) return;
        setState((prev) =>
          prev.status === "ready"
            ? { ...prev, loadingMore: false, loadMoreError: errorMessage(err) }
            : prev,
        );
      });
  }

  function handleRevoked(updated: Consent) {
    setState((prev) =>
      prev.status === "ready"
        ? {
            ...prev,
            items: prev.items.map((c) => (c.id === updated.id ? updated : c)),
          }
        : prev,
    );
    setRevokedNotice(true);
    setRetryToken((n) => n + 1);
  }

  return (
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 motion-reduce:animate-none space-y-8 duration-300">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
            {t("list.title")}
          </h1>
          <p className="text-pretty text-sm text-muted-foreground">
            {t("list.subtitle")}
          </p>
        </div>
        <Button asChild className="min-h-11 shrink-0 sm:min-h-8">
          <Link href="/consent/new">{t("list.grantCta")}</Link>
        </Button>
      </div>

      <div
        role="group"
        aria-label={t("list.views.label")}
        className="flex flex-wrap gap-2"
      >
        {(["active", "history"] as const).map((value) => (
          <Button
            key={value}
            variant={view === value ? "default" : "outline"}
            aria-pressed={view === value}
            onClick={() => {
              paginationRequest.current?.abort();
              setView(value);
            }}
          >
            {t(`list.views.${value}`)}
          </Button>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">
        {t(`list.views.${view}Hint`)}
      </p>

      {revokedNotice && (
        <Alert className="border-consent-active/40 text-consent-active">
          <CircleCheckIcon />
          <AlertTitle>{t("list.revoke.success")}</AlertTitle>
        </Alert>
      )}

      {state.status === "loading" && (
        <div className="space-y-3" role="status" aria-live="polite">
          <span className="sr-only">{t("list.loading")}</span>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      )}

      {state.status === "notFound" && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ShieldCheckIcon />
            </EmptyMedia>
            <EmptyTitle>{t("list.notFound")}</EmptyTitle>
          </EmptyHeader>
        </Empty>
      )}

      {state.status === "error" && (
        <div className="space-y-3">
          <Alert variant="destructive">
            <AlertTitle>{t("list.error.title")}</AlertTitle>
            <AlertDescription>{state.message}</AlertDescription>
          </Alert>
          <Button variant="outline" onClick={() => setRetryToken((n) => n + 1)}>
            {t("list.error.retry")}
          </Button>
        </div>
      )}

      {state.status === "ready" && state.items.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ShieldCheckIcon />
            </EmptyMedia>
            <EmptyTitle>
              {t(
                view === "active"
                  ? "list.views.noActive"
                  : "list.views.noHistory",
              )}
            </EmptyTitle>
            <EmptyDescription>
              {t(
                view === "active"
                  ? "list.views.noActiveBody"
                  : "list.views.noHistoryBody",
              )}
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button asChild className="min-h-11 sm:min-h-8">
              <Link href="/consent/new">{t("list.grantCta")}</Link>
            </Button>
          </EmptyContent>
        </Empty>
      )}

      {state.status === "ready" && state.items.length > 0 && (
        <div className="space-y-4">
          <ul className="space-y-3">
            {state.items.map((consent) => (
              <ConsentRow
                key={consent.id}
                consent={consent}
                onRevoked={handleRevoked}
              />
            ))}
          </ul>

          {state.loadMoreError && (
            <Alert variant="destructive">
              <AlertTitle>{t("list.error.title")}</AlertTitle>
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
              {state.loadingMore ? t("list.loadingMore") : t("list.loadMore")}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
