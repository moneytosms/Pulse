"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Checkbox } from "@/components/ui/Checkbox";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/errors";
import { MANDATORY_NOTIFICATION_TYPES, type NotificationPreference } from "@/lib/notifications";

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

function PreferenceRow({
  pref,
  onSaved,
}: {
  pref: NotificationPreference;
  onSaved: (updated: NotificationPreference) => void;
}) {
  const t = useTranslations("notifications");
  const errorMessage = useApiErrorMessage();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle(enabled: boolean) {
    setSaving(true);
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
      setSaving(false);
    }
  }

  return (
    <li className="space-y-2 rounded-md border border-border bg-surface px-4 py-3">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{typeLabel(pref.notificationType, t)}</p>
          <p className="text-xs text-muted">{channelLabel(pref.channel, t)}</p>
        </div>
        <Checkbox checked={pref.enabled} onCheckedChange={toggle} disabled={saving} />
      </div>
      {error && (
        <Callout tone="error" iconLabel={t("error.title")}>
          {error}
        </Callout>
      )}
    </li>
  );
}

export default function NotificationPreferencesPage() {
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

  return (
    <section className="space-y-6">
      <div className="space-y-1">
        <Link href="/notifications" className="text-sm font-medium text-accent-text underline">
          {t("preferences.back")}
        </Link>
        <h1 className="text-2xl font-bold text-foreground">{t("preferences.title")}</h1>
        <p className="text-sm text-muted">{t("preferences.subtitle")}</p>
      </div>

      {state.status === "loading" && <p className="text-sm text-muted">{t("preferences.loading")}</p>}

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

      {state.status === "ready" && visible.length === 0 && (
        <Callout tone="info" iconLabel={t("preferences.empty.title")}>
          <span className="block font-medium text-foreground">{t("preferences.empty.title")}</span>
          <span>{t("preferences.empty.body")}</span>
        </Callout>
      )}

      {state.status === "ready" && visible.length > 0 && (
        <ul className="space-y-3">
          {visible.map((pref) => (
            <PreferenceRow
              key={`${pref.notificationType}:${pref.channel}`}
              pref={pref}
              onSaved={handleSaved}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
