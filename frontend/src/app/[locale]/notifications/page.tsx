"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { BellIcon, CircleCheckIcon, InfoIcon } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
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
  const Icon = readAt ? CircleCheckIcon : InfoIcon;
  return (
    <Badge
      variant="outline"
      className={readAt ? "text-muted-foreground" : "border-primary text-primary"}
    >
      <Icon className="size-3" />
      {readAt ? t("list.read") : t("list.unread")}
    </Badge>
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
      toast.success(t("list.read"));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setMarking(false);
    }
  }

  return (
    <li className="flex gap-3 rounded-xl border bg-card px-4 py-3 shadow-sm">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
        <BellIcon className="size-4" />
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-medium text-muted-foreground">
            {typeLabel(notification.type, t)}
          </span>
          <ReadBadge readAt={notification.readAt} />
        </div>
        <p className="text-sm font-medium text-pretty text-foreground">{notification.title}</p>
        <p className="text-sm text-pretty text-muted-foreground">{notification.body}</p>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs tabular-nums text-muted-foreground">
            {formatDate(notification.createdAt)}
          </p>
          {!notification.readAt && (
            <Button
              variant="ghost"
              size="sm"
              disabled={marking}
              aria-busy={marking}
              onClick={markRead}
            >
              {marking && <Spinner />}
              {marking ? t("list.marking") : t("list.markRead")}
            </Button>
          )}
        </div>
        {error && (
          <Alert variant="destructive">
            <InfoIcon />
            <AlertTitle>{t("error.title")}</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </div>
    </li>
  );
}

function NotificationListSkeleton() {
  return (
    <ul className="space-y-3" aria-hidden="true">
      {Array.from({ length: 3 }).map((_, i) => (
        <li key={i} className="flex gap-3 rounded-xl border bg-card px-4 py-3 shadow-sm">
          <Skeleton className="size-9 shrink-0 rounded-md" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-20" />
          </div>
        </li>
      ))}
    </ul>
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
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 duration-300 motion-reduce:animate-none space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
            {t("title")}
          </h1>
          <p className="text-sm text-pretty text-muted-foreground">{t("subtitle")}</p>
        </div>
        <Button asChild variant="outline" size="sm" className="shrink-0">
          <Link href="/notifications/preferences">{t("preferencesCta")}</Link>
        </Button>
      </div>

      {state.status === "loading" && (
        <>
          <span className="sr-only">{t("loading")}</span>
          <NotificationListSkeleton />
        </>
      )}

      {state.status === "error" && (
        <div className="space-y-3">
          <Alert variant="destructive">
            <InfoIcon />
            <AlertTitle>{t("error.title")}</AlertTitle>
            <AlertDescription>{state.message}</AlertDescription>
          </Alert>
          <Button variant="outline" onClick={() => setRetryToken((n) => n + 1)}>
            {t("error.retry")}
          </Button>
        </div>
      )}

      {state.status === "ready" && state.items.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <BellIcon />
            </EmptyMedia>
            <EmptyTitle>{t("empty.title")}</EmptyTitle>
            <EmptyDescription>{t("empty.body")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
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
            <Alert variant="destructive">
              <InfoIcon />
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
              className="w-full sm:w-auto"
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
