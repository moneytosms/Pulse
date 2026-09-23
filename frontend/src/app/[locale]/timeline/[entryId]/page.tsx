"use client";

import { use, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { BreakGlassBanner } from "@/components/BreakGlassBanner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ClinicalText } from "@/components/ClinicalText";
import { DocumentViewer } from "@/components/DocumentViewer";
import {
  FlaskConicalIcon,
  NotebookPenIcon,
  PillIcon,
  StethoscopeIcon,
  SyringeIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import type { EntryDetail, EntryType } from "@/lib/records";

const ENTRY_ICONS: Record<EntryType, typeof StethoscopeIcon> = {
  DIAGNOSIS: StethoscopeIcon,
  PRESCRIPTION: PillIcon,
  LAB_REPORT: FlaskConicalIcon,
  PROCEDURE: SyringeIcon,
  CLINICAL_NOTE: NotebookPenIcon,
};

/**
 * "H"/"L" out-of-range flag for a Lab Report. One alert hue (critical/red),
 * never red-versus-green — direction is carried by the ▲/▼ glyph, the
 * letter and the words, not by colour (docs/design-direction.md: "High
 * versus low lab values must not be red versus green").
 */
function labFlag(entry: EntryDetail): "high" | "low" | null {
  if (entry.entryType !== "LAB_REPORT" || entry.valueNumeric == null) return null;
  if (entry.referenceHigh != null && entry.valueNumeric > entry.referenceHigh) return "high";
  if (entry.referenceLow != null && entry.valueNumeric < entry.referenceLow) return "low";
  return null;
}

function AbnormalMarker({ flag }: { flag: "high" | "low" }) {
  const t = useTranslations("timeline");
  const a = t.raw("detail.abnormal") as Record<string, string>;
  return (
    <Badge className="gap-1 border-critical-border bg-critical-surface font-semibold text-critical">
      <span aria-hidden="true">{flag === "high" ? "▲" : "▼"}</span>
      <span>{flag === "high" ? a.high : a.low}</span>
      <span>{flag === "high" ? a.aboveRange : a.belowRange}</span>
    </Badge>
  );
}

type LoadState =
  | { status: "loading" }
  | { status: "notFound" }
  | { status: "error"; message: string }
  | { status: "ready"; entry: EntryDetail };

export default function EntryDetailPage({
  params,
}: {
  params: Promise<{ entryId: string }>;
}) {
  const { entryId } = use(params);
  const t = useTranslations("timeline");
  const errorMessage = useApiErrorMessage();
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    // Deferred one microtask so the reset is a callback, not a direct
    // synchronous setState in the effect body (react-hooks/set-state-in-effect).
    Promise.resolve().then(() => {
      if (active) setState({ status: "loading" });
    });
    api
      .get<EntryDetail>(`/entries/${entryId}`)
      .then((entry) => {
        if (active) setState({ status: "ready", entry });
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
  }, [entryId]);

  return (
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 space-y-8 duration-300 motion-reduce:animate-none">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/timeline">{t("title")}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>
              {state.status === "ready" ? t(`entryTypes.${state.entry.entryType}`) : t("detail.title")}
            </BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <Button asChild variant="link" className="h-auto p-0">
        <Link href="/timeline">{t("detail.back")}</Link>
      </Button>

      {state.status === "loading" && (
        <div className="space-y-4" aria-hidden="true">
          <p className="sr-only">{t("loading")}</p>
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-40 w-full rounded-xl" />
        </div>
      )}

      {state.status === "notFound" && (
        <Alert>
          <AlertTitle>{t("detail.title")}</AlertTitle>
          <AlertDescription>{t("detail.notFound")}</AlertDescription>
        </Alert>
      )}

      {state.status === "error" && (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>{t("error.title")}</AlertTitle>
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      )}

      {state.status === "ready" && (
        <>
          <BreakGlassBanner patientId={state.entry.patientId} />
          <EntryDetailView entry={state.entry} />
        </>
      )}
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-1 px-4 py-3 sm:grid-cols-3 sm:gap-4">
      <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
      <dd className="text-sm text-foreground tabular-nums sm:col-span-2">{children}</dd>
    </div>
  );
}

function EntryDetailView({ entry }: { entry: EntryDetail }) {
  const t = useTranslations("timeline");
  const Icon = ENTRY_ICONS[entry.entryType];
  const f = t.raw("detail.fields") as Record<string, string>;

  const rows: Array<[string, ReactNode]> = [
    [f.occurredAt, formatDate(entry.occurredAt)],
    [f.recordedAt, formatDate(entry.recordedAt)],
  ];

  if (entry.code || entry.displayName) {
    rows.push([
      f.code,
      <ClinicalText key="code">
        {entry.displayName ?? "—"}
        {entry.code ? ` (${entry.codeSystem ?? ""} ${entry.code})` : ""}
      </ClinicalText>,
    ]);
  }
  if (entry.entryType === "LAB_REPORT") {
    const value = entry.valueNumeric != null ? String(entry.valueNumeric) : entry.valueText;
    const flag = labFlag(entry);
    rows.push([
      f.value,
      <span key="value" className="flex flex-wrap items-center gap-2">
        <ClinicalText>
          {value ?? "—"} {entry.unit ?? ""}
        </ClinicalText>
        {flag && <AbnormalMarker flag={flag} />}
      </span>,
    ]);
    if (entry.referenceLow != null || entry.referenceHigh != null) {
      rows.push([
        f.referenceRange,
        <ClinicalText key="range">
          {entry.referenceLow ?? "—"} – {entry.referenceHigh ?? "—"} {entry.unit ?? ""}
        </ClinicalText>,
      ]);
    }
  }
  if (entry.entryType === "PRESCRIPTION") {
    rows.push([f.medication, <ClinicalText key="med">{entry.medicationName ?? "—"}</ClinicalText>]);
    if (entry.dosage) rows.push([f.dosage, <ClinicalText key="dosage">{entry.dosage}</ClinicalText>]);
    if (entry.frequency)
      rows.push([f.frequency, <ClinicalText key="freq">{entry.frequency}</ClinicalText>]);
    if (entry.route) rows.push([f.route, <ClinicalText key="route">{entry.route}</ClinicalText>]);
  }
  if (entry.entryType === "CLINICAL_NOTE" && entry.text) {
    rows.push([f.note, <ClinicalText key="note">{entry.text}</ClinicalText>]);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
          <Icon className="size-4" />
        </span>
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
          {t(`entryTypes.${entry.entryType}`)}
        </h1>
      </div>

      {entry.supersedesId && (
        <Alert>
          <AlertDescription>
            <span>{t("detail.correctsNotice")}</span>{" "}
            <Button asChild variant="link" className="h-auto p-0">
              <Link href={`/timeline/${entry.supersedesId}`}>{t("detail.viewPrevious")}</Link>
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <dl className="divide-y rounded-xl border bg-card shadow-sm">
        {rows.map(([label, value]) => (
          <Field key={label} label={label}>
            {value}
          </Field>
        ))}
      </dl>

      {entry.documents.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-muted-foreground">{f.documents}</h2>
          <ul className="space-y-2">
            {entry.documents.map((doc) => (
              <DocumentViewer key={doc.id} doc={doc} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
