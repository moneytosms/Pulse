"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { TriangleAlertIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import type { AuditEventProjection } from "@/lib/audit";
import { formatDate } from "@/lib/format";
import type { Page } from "@/lib/records";

// Supplementary notice from the same patient-scoped audit projection as the
// history screen. Filter on the server so routine activity cannot bury a
// recent emergency event beyond an arbitrary first-page limit.
const RECENT_WINDOW_MS = 72 * 60 * 60 * 1000;
const BREAK_GLASS_ACTION = "BREAK_GLASS_ACCESS";

export function BreakGlassBanner({ patientId }: { patientId: string }) {
  const t = useTranslations("breakGlass");
  const [event, setEvent] = useState<AuditEventProjection | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const params = new URLSearchParams({ patientId, limit: "1", action: BREAK_GLASS_ACTION, since: new Date(Date.now() - RECENT_WINDOW_MS).toISOString() });
    Promise.resolve().then(() => { if (active) setEvent(null); });
    api
      .get<Page<AuditEventProjection>>(`/audit-events?${params}`, { signal: controller.signal })
      .then((page) => {
        if (!active) return;
        const cutoff = Date.now() - RECENT_WINDOW_MS;
        const recent = page.items.find(
          (item) =>
            item.action === BREAK_GLASS_ACTION && new Date(item.occurredAt).getTime() >= cutoff,
        );
        setEvent(recent ?? null);
      })
      .catch(() => {
        // Silent — this is a supplementary notice, not the primary audit
        // view, and must never block or error the record screen it sits on.
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [patientId]);

  if (!event) return null;

  return (
    <Alert className="border-break-glass/40 bg-break-glass-surface text-break-glass animate-in fade-in-0 slide-in-from-bottom-1 motion-reduce:animate-none duration-300">
      <TriangleAlertIcon />
      <AlertTitle>{t("title")}</AlertTitle>
      <AlertDescription className="text-break-glass/90">
        {t("body", { date: formatDate(event.occurredAt) })}{" "}
        <Link href="/audit" className="font-medium underline underline-offset-4">
          {t("viewAudit")}
        </Link>
      </AlertDescription>
    </Alert>
  );
}
