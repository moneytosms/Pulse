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

// A break-glass access is time-boxed, justified and CRITICAL-audited
// (docs/domain-model.md, delivery-plan.md), and the Patient is notified
// immediately. There is no `NotificationType` for it yet in the provisional
// schema (`lib/notifications.ts`), so this banner reads the same audit
// projection the "who accessed my records" screen uses
// (.claude/rules/clinical-safety.md: never a second, uncontrolled copy of
// the event) and looks for a recent `BREAK_GLASS_ACCESS` row. Distinct from
// the daily digest — this is a persistent, dismiss-free callout on the
// Patient's own record views, not a rolled-up notification.
const RECENT_WINDOW_MS = 72 * 60 * 60 * 1000;
const BREAK_GLASS_ACTION = "BREAK_GLASS_ACCESS";
const CHECK_LIMIT = 5;

export function BreakGlassBanner({ patientId }: { patientId: string }) {
  const t = useTranslations("breakGlass");
  const [event, setEvent] = useState<AuditEventProjection | null>(null);

  useEffect(() => {
    let active = true;
    api
      .get<Page<AuditEventProjection>>(
        `/audit-events?patientId=${patientId}&limit=${CHECK_LIMIT}`,
      )
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
