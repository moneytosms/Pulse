"use client";

import { use, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Callout } from "@/components/ui/Callout";
import { ClinicalText } from "@/components/ClinicalText";
import { DocumentViewer } from "@/components/DocumentViewer";
import {
  ClinicalNoteIcon,
  DiagnosisIcon,
  FlaskIcon,
  PrescriptionIcon,
  ProcedureIcon,
} from "@/components/ui/icons";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";
import type { EntryDetail, EntryType } from "@/lib/records";

// Clinician-facing entry detail, mirroring `timeline/[entryId]/page.tsx`
// against the same `/entries/{entryId}` endpoint. The notFound branch below
// is deliberately the *only* failure rendering: a consent-denied read and a
// nonexistent entry are the same backend 404 (clinical-safety.md) and must
// look identical here too — no message ever says "you don't have consent".
const ENTRY_ICONS: Record<EntryType, typeof DiagnosisIcon> = {
  DIAGNOSIS: DiagnosisIcon,
  PRESCRIPTION: PrescriptionIcon,
  LAB_REPORT: FlaskIcon,
  PROCEDURE: ProcedureIcon,
  CLINICAL_NOTE: ClinicalNoteIcon,
};

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
    <span className="inline-flex items-center gap-1 rounded-full border border-critical-border bg-critical-surface px-2 py-0.5 text-xs font-semibold text-critical">
      <span aria-hidden="true">{flag === "high" ? "▲" : "▼"}</span>
      <span>{flag === "high" ? a.high : a.low}</span>
      <span>{flag === "high" ? a.aboveRange : a.belowRange}</span>
    </span>
  );
}

type LoadState =
  | { status: "loading" }
  | { status: "notFound" }
  | { status: "error"; message: string }
  | { status: "ready"; entry: EntryDetail };

export default function ClinicianEntryDetailPage({
  params,
}: {
  params: Promise<{ patientId: string; entryId: string }>;
}) {
  const { patientId, entryId } = use(params);
  const t = useTranslations("timeline");
  const tClinician = useTranslations("clinicianRecords");
  const errorMessage = useApiErrorMessage();
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let active = true;
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
    <section className="space-y-6">
      <Link
        href={`/patients/${patientId}/records`}
        className="text-sm font-medium text-accent-text underline"
      >
        {tClinician("detail.back")}
      </Link>

      {state.status === "loading" && <p className="text-sm text-muted">{t("loading")}</p>}

      {state.status === "notFound" && (
        <Callout tone="info" iconLabel={tClinician("notFound.title")}>
          {tClinician("notFound.body")}
        </Callout>
      )}

      {state.status === "error" && (
        <Callout tone="error" iconLabel={tClinician("error.title")}>
          {state.message}
        </Callout>
      )}

      {state.status === "ready" && <EntryDetailView entry={state.entry} patientId={patientId} />}
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-1 px-4 py-3 sm:grid-cols-3 sm:gap-4">
      <dt className="text-sm font-medium text-muted">{label}</dt>
      <dd className="text-sm text-foreground sm:col-span-2">{children}</dd>
    </div>
  );
}

function EntryDetailView({ entry, patientId }: { entry: EntryDetail; patientId: string }) {
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
      <div className="flex items-center gap-2">
        <Icon className="size-6 shrink-0 text-muted" />
        <h1 className="text-2xl font-bold text-foreground">
          {t(`entryTypes.${entry.entryType}`)}
        </h1>
      </div>

      {entry.supersedesId && (
        <Callout tone="info" iconLabel={t("detail.title")}>
          <span>{t("detail.correctsNotice")}</span>{" "}
          <Link
            href={`/patients/${patientId}/records/${entry.supersedesId}`}
            className="font-medium underline"
          >
            {t("detail.viewPrevious")}
          </Link>
        </Callout>
      )}

      <dl className="divide-y divide-border rounded-md border border-border bg-surface">
        {rows.map(([label, value]) => (
          <Field key={label} label={label}>
            {value}
          </Field>
        ))}
      </dl>

      {entry.documents.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-muted">{f.documents}</h2>
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
