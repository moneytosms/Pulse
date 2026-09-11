"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { CheckCircleIcon, ClockIcon, XCircleIcon } from "@/components/ui/icons";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import type { Consent, ConsentStatus, RevocationRequest } from "@/lib/consent";
import { useApiErrorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import type { Page } from "@/lib/records";

// Icon + label per status — colour never carries meaning alone
// (.claude/rules/frontend.md).
const STATUS_ICONS: Record<ConsentStatus, typeof CheckCircleIcon> = {
  ACTIVE: CheckCircleIcon,
  REVOKED: XCircleIcon,
  EXPIRED: ClockIcon,
};

const STATUS_CLASSES: Record<ConsentStatus, string> = {
  ACTIVE: "border-consent-active bg-consent-active-surface text-consent-active",
  REVOKED: "border-critical-border bg-critical-surface text-consent-revoked",
  EXPIRED: "border-border-strong bg-consent-expired-surface text-consent-expired",
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
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[status]}`}
    >
      <Icon className="size-3.5" />
      {t(`list.status.${status}`)}
    </span>
  );
}

function scopeSummary(
  consent: Consent,
  t: ReturnType<typeof useTranslations<"consent">>,
  tTimeline: ReturnType<typeof useTranslations<"timeline">>,
): { types: string; window: string } {
  const types = consent.entryTypes?.length
    ? consent.entryTypes.map((type) => tTimeline(`entryTypes.${type}`)).join(", ")
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
      <Button variant="secondary" onClick={() => setConfirming(true)} className="shrink-0">
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
    <div className="w-full space-y-2 rounded-md border border-border-strong bg-surface-raised p-3 sm:w-72">
      <p className="text-sm font-medium text-foreground">{t("list.revoke.confirmTitle")}</p>
      <p className="text-xs text-muted">{t("list.revoke.confirmBody")}</p>
      <label className="block space-y-1 text-xs text-muted">
        {t("list.revoke.reasonLabel")}
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="block w-full rounded-md border border-border-strong bg-surface px-2 py-1.5 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        />
      </label>
      {error && (
        <Callout tone="error" iconLabel={t("list.revoke.action")}>
          {error}
        </Callout>
      )}
      <div className="flex gap-2">
        <Button loading={submitting} onClick={confirmRevoke} className="flex-1">
          {submitting ? t("list.revoke.revoking") : t("list.revoke.confirm")}
        </Button>
        <Button
          variant="secondary"
          onClick={() => setConfirming(false)}
          disabled={submitting}
          className="flex-1"
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
  const t = useTranslations("consent");
  const tTimeline = useTranslations("timeline");
  const { types, window } = scopeSummary(consent, t, tTimeline);

  return (
    <li className="space-y-3 rounded-md border border-border bg-surface px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-foreground">
          {consent.granteeName ?? consent.granteeUserId}
        </span>
        <StatusBadge status={consent.status} />
      </div>

      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted">{t("list.fields.purpose")}</dt>
          <dd className="text-foreground">
            {t(`list.purpose.${consent.purpose}`)}
            {consent.purpose === "OTHER" && consent.purposeText ? ` — ${consent.purposeText}` : ""}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{t("list.fields.scope")}</dt>
          <dd className="text-foreground">
            {types}
            <span className="text-muted"> · {window}</span>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{t("list.fields.granted")}</dt>
          <dd className="text-foreground">{formatDate(consent.grantedAt)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">
            {consent.status === "REVOKED" ? t("list.fields.revokedAt") : t("list.fields.expires")}
          </dt>
          <dd className="text-foreground">
            {consent.status === "REVOKED" && consent.revokedAt
              ? formatDate(consent.revokedAt)
              : formatDate(consent.expiresAt)}
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

  const [patientId, setPatientId] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [revokedNotice, setRevokedNotice] = useState(false);

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
      .get<Page<Consent>>(`/consents?patientId=${patientId}&limit=${LIMIT}`)
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
      .get<Page<Consent>>(`/consents?patientId=${patientId}&limit=${LIMIT}&cursor=${cursor}`)
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
  }

  return (
    <section className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-foreground">{t("list.title")}</h1>
          <p className="text-sm text-muted">{t("list.subtitle")}</p>
        </div>
        <Link
          href="/consent/new"
          className="shrink-0 text-sm font-medium text-accent-text underline"
        >
          {t("list.grantCta")}
        </Link>
      </div>

      {revokedNotice && (
        <Callout tone="success" iconLabel={t("list.revoke.action")}>
          {t("list.revoke.success")}
        </Callout>
      )}

      {state.status === "loading" && <p className="text-sm text-muted">{t("list.loading")}</p>}

      {state.status === "notFound" && (
        <Callout tone="info" iconLabel={t("list.title")}>
          {t("list.notFound")}
        </Callout>
      )}

      {state.status === "error" && (
        <div className="space-y-3">
          <Callout tone="error" iconLabel={t("list.error.title")}>
            {state.message}
          </Callout>
          {patientId && (
            <Button variant="secondary" onClick={() => setRetryToken((n) => n + 1)}>
              {t("list.error.retry")}
            </Button>
          )}
        </div>
      )}

      {state.status === "ready" && state.items.length === 0 && (
        <Callout tone="info" iconLabel={t("list.empty.title")}>
          <span className="block font-medium text-foreground">{t("list.empty.title")}</span>
          <span>{t("list.empty.body")}</span>
        </Callout>
      )}

      {state.status === "ready" && state.items.length > 0 && (
        <div className="space-y-4">
          <ul className="space-y-3">
            {state.items.map((consent) => (
              <ConsentRow key={consent.id} consent={consent} onRevoked={handleRevoked} />
            ))}
          </ul>

          {state.loadMoreError && (
            <Callout tone="error" iconLabel={t("list.error.title")}>
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
              {state.loadingMore ? t("list.loadingMore") : t("list.loadMore")}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
