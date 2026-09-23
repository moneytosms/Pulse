"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import {
  ActivityIcon,
  FlaskConicalIcon,
  InfoIcon,
  PillIcon,
  TriangleAlertIcon,
} from "lucide-react";
import type { BarDatum } from "@/components/charts/BarChart";
import type { LinePoint } from "@/components/charts/LineChart";
import { ClinicalText } from "@/components/ClinicalText";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useRouter } from "@/i18n/navigation";
import type {
  DataQualityFlag,
  LabTest,
  LabTrendPoint,
  MedicationSummary,
  MonthlyVisitCount,
  ProviderEntryCount,
} from "@/lib/analytics";
import { api, ApiError } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/errors";
import { formatDate, formatNumber } from "@/lib/format";

// Patient-facing analytics screen (issue #55). Every series here reads
// clinical data (`RECORDS_READ`) except data-quality flags
// (`ANALYTICS_DATA_QUALITY_READ`) — both permissions are the Patient's own,
// so this page only ever renders the signed-in patient's own analytics
// (`/patients/{id}/analytics/...`), the same `patient_id` `lib/records.ts`
// screens already resolve via `/patients/me`.
//
// Data-quality flags are informational only, never blocking
// (`backend/app/modules/analytics/schemas.py` docstring) — rendered as a
// plain list, never gating anything else on this page.

// recharts is heavy — load both chart components client-side only, after
// the page shell (stat cards, data-quality alert) has already painted.
const ChartSkeleton = () => <Skeleton className="h-40 w-full" />;
const BarChart = dynamic(
  () => import("@/components/charts/BarChart").then((m) => m.BarChart),
  { ssr: false, loading: ChartSkeleton },
);
const LineChart = dynamic(
  () => import("@/components/charts/LineChart").then((m) => m.LineChart),
  { ssr: false, loading: ChartSkeleton },
);

const FLAG_ICON: Record<DataQualityFlag, typeof InfoIcon> = {
  MISSING_DOB: InfoIcon,
  MISSING_CONTACT: InfoIcon,
  FUTURE_DATED_ENTRY: TriangleAlertIcon,
  IMPLAUSIBLE_DOB: TriangleAlertIcon,
  UNCLAIMED_LONG_LIVED: InfoIcon,
};

// Lab trend: `/analytics/lab-tests` lists the patient's distinct tests for a
// picker (default: the first); the chosen (codeSystem, code) pair drives
// `/analytics/lab-trend`. Test names are clinical content, shown as recorded.
// A patient with no lab reports gets no trend section, and a failed trend
// load never fails the rest of the page.
const testKey = (test: LabTest) => `${test.codeSystem}|${test.code}`;

interface Loaded {
  visitFrequency: MonthlyVisitCount[];
  activeMedications: MedicationSummary[];
  providerEntryCounts: ProviderEntryCount[];
  dataQualityFlags: DataQualityFlag[];
  labTests: LabTest[];
}

type LoadState =
  | { status: "loading" }
  | { status: "notFound" }
  | { status: "error"; message: string }
  | { status: "ready"; data: Loaded };

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof ActivityIcon;
  label: string;
  value: number;
}) {
  return (
    <Card size="sm">
      <CardContent className="flex items-center gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Icon className="size-4" />
        </div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-xl font-semibold tabular-nums text-foreground">
            {formatNumber(value)}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-8" aria-hidden="true">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} size="sm">
            <CardContent className="flex items-center gap-3">
              <Skeleton className="size-9 shrink-0 rounded-md" />
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-5 w-10" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-4 w-32" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-40 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const t = useTranslations("analytics");
  const errorMessage = useApiErrorMessage();
  const router = useRouter();

  const [patientId, setPatientId] = useState<string | null>(null);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedTest, setSelectedTest] = useState("");
  const [labTrend, setLabTrend] = useState<LabTrendPoint[] | null>(null);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!patientId) return;
    let active = true;
    const base = `/patients/${patientId}/analytics`;

    Promise.all([
      api.get<MonthlyVisitCount[]>(`${base}/visit-frequency`),
      api.get<MedicationSummary[]>(`${base}/active-medications`),
      api.get<ProviderEntryCount[]>(`${base}/provider-entry-counts`),
      api.get<DataQualityFlag[]>(`${base}/data-quality-flags`),
      api.get<LabTest[]>(`${base}/lab-tests`).catch(() => [] as LabTest[]),
    ])
      .then(([visitFrequency, activeMedications, providerEntryCounts, dataQualityFlags, labTests]) => {
        if (!active) return;
        setSelectedTest(labTests[0] ? testKey(labTests[0]) : "");
        setState({
          status: "ready",
          data: {
            visitFrequency,
            activeMedications,
            providerEntryCounts,
            dataQualityFlags,
            labTests,
          },
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  useEffect(() => {
    if (!patientId || !selectedTest) return;
    let active = true;
    const [codeSystem, code] = selectedTest.split("|");
    const params = new URLSearchParams({ codeSystem, code });
    api
      .get<LabTrendPoint[]>(`/patients/${patientId}/analytics/lab-trend?${params}`)
      .then((points) => {
        if (active) setLabTrend(points);
      })
      .catch(() => {
        if (active) setLabTrend(null);
      });
    return () => {
      active = false;
    };
  }, [patientId, selectedTest]);

  const selectedLabTest =
    state.status === "ready"
      ? state.data.labTests.find((test) => testKey(test) === selectedTest)
      : undefined;

  return (
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 duration-300 motion-reduce:animate-none space-y-8">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
          {t("title")}
        </h1>
        <p className="text-sm text-pretty text-muted-foreground">{t("subtitle")}</p>
      </div>

      {state.status === "loading" && (
        <>
          <span className="sr-only">{t("loading")}</span>
          <DashboardSkeleton />
        </>
      )}

      {state.status === "notFound" && (
        <Alert>
          <InfoIcon />
          <AlertTitle>{t("title")}</AlertTitle>
          <AlertDescription>{t("notFound")}</AlertDescription>
        </Alert>
      )}

      {state.status === "error" && (
        <Alert variant="destructive">
          <InfoIcon />
          <AlertTitle>{t("error.title")}</AlertTitle>
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      )}

      {state.status === "ready" && (
        <div className="space-y-8">
          {/* Stat cards row (dashboard-01 style) — derived from the same
              series rendered below, no extra API calls. */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              icon={ActivityIcon}
              label={t("stats.totalVisits")}
              value={state.data.visitFrequency.reduce((sum, row) => sum + row.count, 0)}
            />
            <StatCard
              icon={PillIcon}
              label={t("stats.activeMedications")}
              value={state.data.activeMedications.length}
            />
            <StatCard
              icon={FlaskConicalIcon}
              label={t("stats.labTestsTracked")}
              value={state.data.labTests.length}
            />
            <StatCard
              icon={TriangleAlertIcon}
              label={t("stats.dataQualityFlags")}
              value={state.data.dataQualityFlags.length}
            />
          </div>

          {state.data.dataQualityFlags.length > 0 && (
            <Alert>
              <InfoIcon />
              <AlertTitle>{t("dataQuality.title")}</AlertTitle>
              <AlertDescription>
                <p>{t("dataQuality.hint")}</p>
                <ul className="mt-2 space-y-1.5">
                  {state.data.dataQualityFlags.map((flag) => {
                    const Icon = FLAG_ICON[flag];
                    return (
                      <li key={flag} className="flex items-start gap-2 text-foreground">
                        <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                        <span>{t(`dataQuality.flags.${flag}`)}</span>
                      </li>
                    );
                  })}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {/* Chart cards grid */}
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium">
                  {t("visitFrequency.title")}
                </CardTitle>
              </CardHeader>
              <CardContent className="min-h-40">
                {state.data.visitFrequency.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t("empty")}</p>
                ) : (
                  <BarChart
                    ariaLabel={t("visitFrequency.title")}
                    formatValue={formatNumber}
                    data={state.data.visitFrequency.map(
                      (row): BarDatum => ({
                        label: formatDate(row.month),
                        value: row.count,
                      }),
                    )}
                  />
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium">
                  {t("providerEntryCounts.title")}
                </CardTitle>
              </CardHeader>
              <CardContent className="min-h-40">
                {state.data.providerEntryCounts.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t("empty")}</p>
                ) : (
                  <BarChart
                    ariaLabel={t("providerEntryCounts.title")}
                    formatValue={formatNumber}
                    data={state.data.providerEntryCounts.map(
                      (row, i): BarDatum => ({
                        label: row.providerId
                          ? t("providerEntryCounts.providerLabel", { n: i + 1 })
                          : t("providerEntryCounts.unknown"),
                        value: row.count,
                      }),
                    )}
                  />
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base font-medium">
                {t("activeMedications.title")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {state.data.activeMedications.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("empty")}</p>
              ) : (
                <ul className="divide-y divide-border">
                  {state.data.activeMedications.map((med, i) => (
                    <li key={i} className="flex flex-col gap-0.5 py-2 text-sm">
                      <span className="font-medium text-foreground">
                        <ClinicalText>{med.medicationName}</ClinicalText>
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {[med.dosage, med.frequency, med.route]
                          .filter((v): v is string => Boolean(v))
                          .map((v, idx, arr) => (
                            <span key={idx}>
                              <ClinicalText>{v}</ClinicalText>
                              {idx < arr.length - 1 ? " · " : ""}
                            </span>
                          ))}
                      </span>
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {formatDate(med.occurredAt)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {state.data.labTests.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium">{t("labTrend.title")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="max-w-xs space-y-1.5">
                  <Label htmlFor="analytics-lab-test">{t("labTrend.picker")}</Label>
                  <Select value={selectedTest} onValueChange={setSelectedTest}>
                    <SelectTrigger id="analytics-lab-test" className="w-full">
                      <SelectValue placeholder={t("labTrend.picker")}>
                        {selectedLabTest ? (
                          <ClinicalText>{selectedLabTest.displayName}</ClinicalText>
                        ) : undefined}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {state.data.labTests.map((test) => (
                        <SelectItem key={testKey(test)} value={testKey(test)}>
                          <ClinicalText>{test.displayName}</ClinicalText>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {labTrend && labTrend.length > 0 ? (
                  <>
                    <LineChart
                      ariaLabel={t("labTrend.title")}
                      data={labTrend.map(
                        (p): LinePoint => ({
                          x: formatDate(p.occurredAt),
                          value: p.valueNumeric ?? 0,
                          abnormal: p.isAbnormal ?? false,
                        }),
                      )}
                    />
                    <ul className="space-y-1.5 text-sm">
                      {labTrend
                        .filter((p) => p.isAbnormal)
                        .map((p, i) => (
                          <li
                            key={i}
                            className="flex items-center gap-2 rounded-md border border-critical-border bg-critical-surface px-2 py-1 text-critical"
                          >
                            <TriangleAlertIcon className="size-4 shrink-0" />
                            <span className="tabular-nums">
                              {formatDate(p.occurredAt)} —{" "}
                              {p.referenceHigh != null && (p.valueNumeric ?? 0) > p.referenceHigh
                                ? t("labTrend.aboveRange")
                                : t("labTrend.belowRange")}
                            </span>
                          </li>
                        ))}
                    </ul>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">{t("empty")}</p>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </section>
  );
}
