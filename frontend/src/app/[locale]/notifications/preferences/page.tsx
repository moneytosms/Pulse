"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { InfoIcon } from "lucide-react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/errors";
import {
  MANDATORY_NOTIFICATION_TYPES,
  NOTIFICATION_CHANNELS,
  type NotificationPreference,
} from "@/lib/notifications";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; items: NotificationPreference[] };

function typeLabel(
  type: string,
  t: ReturnType<typeof useTranslations<"notifications">>,
): string {
  const key = `list.types.${type}`;
  return t.has(key) ? t(key) : type;
}

function channelLabel(
  channel: string,
  t: ReturnType<typeof useTranslations<"notifications">>,
): string {
  const key = `preferences.channels.${channel}`;
  return t.has(key) ? t(key) : channel;
}

function TypeCard({
  type,
  prefs,
  onSaved,
}: {
  type: string;
  prefs: NotificationPreference[];
  onSaved: (updated: NotificationPreference) => void;
}) {
  const t = useTranslations("notifications");
  const errorMessage = useApiErrorMessage();
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(pref: NotificationPreference, enabled: boolean) {
    setSaving(pref.channel);
    setError(null);
    try {
      const updated = await api.put<NotificationPreference>("/notification-preferences", {
        ...pref,
        enabled,
      });
      onSaved(updated);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-medium">{typeLabel(type, t)}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {prefs.map((pref) => {
          const id = `pref-${type}-${pref.channel}`;
          return (
            <div key={pref.channel} className="flex items-center justify-between gap-4">
              <Label htmlFor={id} className="text-sm font-normal text-foreground">
                {channelLabel(pref.channel, t)}
              </Label>
              <Switch
                id={id}
                checked={pref.enabled}
                onCheckedChange={(checked) => toggle(pref, checked === true)}
                disabled={saving === pref.channel}
              />
            </div>
          );
        })}
        {error && (
          <Alert variant="destructive">
            <InfoIcon />
            <AlertTitle>{t("error.title")}</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}

function PreferencesSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      {Array.from({ length: 3 }).map((_, i) => (
        <Card key={i}>
          <CardHeader>
            <Skeleton className="h-4 w-32" />
          </CardHeader>
          <CardContent className="space-y-3">
            {NOTIFICATION_CHANNELS.map((c) => (
              <div key={c} className="flex items-center justify-between gap-4">
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-5 w-8 rounded-full" />
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function NotificationPreferencesPage() {
  const t = useTranslations("notifications");
  const tNav = useTranslations("nav");
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
      .get<NotificationPreference[]>("/notification-preferences")
      .then((items) => {
        if (active) setState({ status: "ready", items });
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

  function handleSaved(updated: NotificationPreference) {
    setState((prev) =>
      prev.status === "ready"
        ? {
            ...prev,
            items: prev.items.map((p) =>
              p.notificationType === updated.notificationType && p.channel === updated.channel
                ? updated
                : p,
            ),
          }
        : prev,
    );
  }

  // Mandatory types (break-glass, consent revocation) never get a
  // preference row on the backend and must not appear here at all — not
  // shown disabled, absent (.claude/rules/clinical-safety.md,
  // `backend/app/modules/notifications/service.py` MANDATORY_TYPES). The
  // backend already omits them from `list_preferences`; this filter is a
  // second, defensive layer against the same leak.
  const visible =
    state.status === "ready"
      ? state.items.filter((pref) => !MANDATORY_NOTIFICATION_TYPES.has(pref.notificationType))
      : [];

  // Group by type for the card-per-type layout — mobile-first (patient
  // pages), so a table that scrolls horizontally at 375px is not an option.
  // The preference list is small (a handful of types × channels), so a
  // plain reduce on every render is cheaper than memoizing it.
  const byType = new Map<string, NotificationPreference[]>();
  for (const pref of visible) {
    const existing = byType.get(pref.notificationType) ?? [];
    existing.push(pref);
    byType.set(pref.notificationType, existing);
  }

  return (
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 duration-300 motion-reduce:animate-none space-y-8">
      <div className="space-y-3">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link href="/notifications">{tNav("notifications")}</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{t("preferences.title")}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
            {t("preferences.title")}
          </h1>
          <p className="text-sm text-pretty text-muted-foreground">{t("preferences.subtitle")}</p>
        </div>
      </div>

      {state.status === "loading" && (
        <>
          <span className="sr-only">{t("preferences.loading")}</span>
          <PreferencesSkeleton />
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

      {state.status === "ready" && visible.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <InfoIcon />
            </EmptyMedia>
            <EmptyTitle>{t("preferences.empty.title")}</EmptyTitle>
            <EmptyDescription>{t("preferences.empty.body")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}

      {state.status === "ready" && visible.length > 0 && (
        <div className="space-y-4">
          {Array.from(byType.entries()).map(([type, prefs]) => (
            <TypeCard key={type} type={type} prefs={prefs} onSaved={handleSaved} />
          ))}
        </div>
      )}
    </section>
  );
}
