"use client";

import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { TriangleAlertIcon } from "lucide-react";
import { ClinicalText } from "@/components/ClinicalText";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate } from "@/lib/format";
import type { LabTrendPoint } from "@/lib/analytics";

const LineChart = dynamic(
  () => import("@/components/charts/LineChart").then((m) => m.LineChart),
  {
    ssr: false,
    loading: () => <Skeleton className="h-40 w-full" />,
  },
);

export function LabTrendResults({ points }: { points: LabTrendPoint[] }) {
  const t = useTranslations("analytics");
  // Numeric measurements are comparable only within their recorded unit.
  // Qualitative or missing results never become fabricated zero values.
  const series = new Map<
    string | null,
    Array<LabTrendPoint & { valueNumeric: number }>
  >();
  for (const point of points) {
    if (point.valueNumeric == null) continue;
    const unit = point.unit ?? null;
    const group = series.get(unit) ?? [];
    group.push({ ...point, valueNumeric: point.valueNumeric });
    series.set(unit, group);
  }
  return (
    <div className="space-y-4">
      {Array.from(series, ([unit, measurements]) => (
        <div
          key={JSON.stringify(unit)}
          data-testid="lab-numeric-series"
          className="space-y-2"
        >
          <h3 className="text-sm font-medium">
            <ClinicalText>{unit ?? t("labTrend.unitUnknown")}</ClinicalText>
          </h3>
          <LineChart
            ariaLabel={t("labTrend.series", {
              unit: unit ?? t("labTrend.unitUnknown"),
            })}
            data={measurements.map((p) => ({
              x: formatDate(p.occurredAt),
              value: p.valueNumeric,
              abnormal: p.isAbnormal ?? false,
            }))}
          />
        </div>
      ))}
      <Table aria-label={t("labTrend.results")}>
        <TableHeader>
          <TableRow>
            <TableHead>{t("labTrend.date")}</TableHead>
            <TableHead>{t("labTrend.value")}</TableHead>
            <TableHead>{t("labTrend.unit")}</TableHead>
            <TableHead>{t("labTrend.referenceRange")}</TableHead>
            <TableHead>{t("labTrend.status")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {points.map((p, i) => (
            <TableRow key={`${p.occurredAt}-${i}`}>
              <TableCell>{formatDate(p.occurredAt)}</TableCell>
              <TableCell>
                <ClinicalText>
                  {p.valueNumeric != null
                    ? String(p.valueNumeric)
                    : (p.valueText ?? t("labTrend.missing"))}
                </ClinicalText>
              </TableCell>
              <TableCell>
                <ClinicalText>
                  {p.unit ?? t("labTrend.unitUnknown")}
                </ClinicalText>
              </TableCell>
              <TableCell>
                <ClinicalText>
                  {p.referenceLow ?? "—"} – {p.referenceHigh ?? "—"}
                </ClinicalText>
              </TableCell>
              <TableCell>
                {p.isAbnormal ? (
                  <span className="inline-flex items-center gap-1 text-critical">
                    <TriangleAlertIcon
                      className="size-4 shrink-0"
                      aria-hidden="true"
                    />
                    {p.valueNumeric != null &&
                    p.referenceHigh != null &&
                    p.valueNumeric > p.referenceHigh
                      ? t("labTrend.aboveRange")
                      : t("labTrend.belowRange")}
                  </span>
                ) : p.isAbnormal === false ? (
                  t("labTrend.withinRange")
                ) : (
                  "—"
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
