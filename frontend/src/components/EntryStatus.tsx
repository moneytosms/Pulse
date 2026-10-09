"use client";

import { useTranslations } from "next-intl";
import { CircleAlertIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Link } from "@/i18n/navigation";
import type { EntryDetail } from "@/lib/records";

export function EntryStatus({
  entry,
  hrefPrefix,
}: {
  entry: EntryDetail;
  hrefPrefix: string;
}) {
  const t = useTranslations("timeline");
  return (
    <div className="space-y-3">
      {entry.isCritical && (
        <Badge className="gap-1 border-critical-border bg-critical-surface text-critical">
          <CircleAlertIcon className="size-4" aria-hidden="true" />
          {t("critical")}
        </Badge>
      )}
      {entry.supersededById && (
        <Alert>
          <CircleAlertIcon />
          <AlertDescription>
            <span>{t("detail.supersededNotice")}</span>{" "}
            <Link
              href={`${hrefPrefix}/${entry.supersededById}`}
              className="font-medium underline underline-offset-4"
            >
              {t("detail.viewCurrent")}
            </Link>
          </AlertDescription>
        </Alert>
      )}
      {entry.supersedesId && (
        <Alert>
          <AlertDescription>
            <span>{t("detail.correctsNotice")}</span>{" "}
            <Link
              href={`${hrefPrefix}/${entry.supersedesId}`}
              className="font-medium underline underline-offset-4"
            >
              {t("detail.viewPrevious")}
            </Link>
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
