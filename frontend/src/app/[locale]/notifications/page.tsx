"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { CheckCircleIcon, InfoIcon } from "@/components/ui/icons";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import type { Notification } from "@/lib/notifications";
import type { Page } from "@/lib/records";

const LIMIT = 20;

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      items: Notification[];
      nextCursor: string | null;
      loadingMore: boolean;
      loadMoreError: string | null;
    };

// Read/unread pairs an icon with the localized label — colour never carries
// meaning alone (.claude/rules/frontend.md).
function ReadBadge({ readAt }: { readAt: string | null }) {
  const t = useTranslations("notifications");
  const Icon = readAt ? CheckCircleIcon : InfoIcon;
  const className = readAt
    ? "inline-flex items-center gap-1 rounded-full border border-border-strong bg-surface-raised px-2 py-0.5 text-xs font-medium text-muted"
    : "inline-flex items-center gap-1 rounded-full border border-accent bg-accent-subtle px-2 py-0.5 text-xs font-medium text-accent-text";
  return (
    <span className={className}>
      <Icon className="size-3.5" />
      {readAt ? t("list.read") : t("list.unread")}
    </span>
  );
}

function typeLabel(
  type: string,
  t: ReturnType<typeof useTranslations<"notifications">>,
): string {
  const key = `list.types.${type}`;
  return t.has(key) ? t(key) : type;
}

function NotificationRow({
  notification,
  onRead,
}: {
  notification: Notification;
  onRead: (id: string, updated: Notification) => void;
}) {
  const t = useTranslations("notifications");
  const errorMessage = useApiErrorMessage();
  const [marking, setMarking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function markRead() {
    setMarking(true);
    setError(null);
    try {
      const updated = await api.post<Notification>(`/notifications/${notification.id}/read`);
      onRead(notification.id, updated);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setMarking(false);
    }
  }

  return (
    <li className="space-y-1 rounded-md border border-border bg-surface px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted">
          {typeLabel(notification.type, t)}
        </span>
        <ReadBadge readAt={notification.readAt} />
      </div>
      <p className="text-sm font-medium text-foreground">{notification.title}</p>
      <p className="text-sm text-muted">{notification.body}</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted">{formatDate(notification.createdAt)}</p>
        {!notification.readAt && (
          <Button variant="ghost" loading={marking} onClick={markRead} className="min-h-0 px-2 py-1">
            {marking ? t("list.marking") : t("list.markRead")}
          </Button>
        )}
      </div>
      {error && (
        <Callout tone="error" iconLabel={t("error.title")}>
          {error}
        </Callout>
      )}
    </li>
  );
}

export default function NotificationsPage() {
  const t = useTranslations("notifications");
  const errorMessage = useApiErrorMessage();
  const router = useRouter();

  const [retryToken, setRetryToken] = useState(0);
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (active) setState({ status: "loading" });
    });
    api
      .get<Page<Notification>>(`/notifications?limit=${LIMIT}`)
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
  }, [retryToken]);

  function handleRead(id: string, updated: Notification) {
    setState((prev) =>
      prev.status === "ready"
        ? { ...prev, items: prev.items.map((n) => (n.id === id ? updated : n)) }
        : prev,
    );
  }

  function loadMore() {
    if (state.status !== "ready" || !state.nextCursor) return;
    const cursor = state.nextCursor;
    setState({ ...state, loadingMore: true, loadMoreError: null });
    api
      .get<Page<Notification>>(`/notifications?limit=${LIMIT}&cursor=${cursor}`)
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

  return (
    <section className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-foreground">{t("title")}</h1>
          <p className="text-sm text-muted">{t("subtitle")}</p>
        </div>
        <Link
          href="/notifications/preferences"
          className="shrink-0 text-sm font-medium text-accent-text underline"
        >
          {t("preferencesCta")}
        </Link>
      </div>

      {state.status === "loading" && <p className="text-sm text-muted">{t("loading")}</p>}

      {state.status === "error" && (
        <div className="space-y-3">
          <Callout tone="error" iconLabel={t("error.title")}>
            {state.message}
          </Callout>
          <Button variant="secondary" onClick={() => setRetryToken((n) => n + 1)}>
            {t("error.retry")}
          </Button>
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
          <ul className="space-y-3">
            {state.items.map((notification) => (
              <NotificationRow
                key={notification.id}
                notification={notification}
                onRead={handleRead}
              />
            ))}
          </ul>

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
