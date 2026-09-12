"use client";

import { use, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { ClinicalText } from "@/components/ClinicalText";
import {
  AlertTriangleIcon,
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
import { ENTRY_TYPES, type EntrySummary, type EntryType, type Page } from "@/lib/records";

// Clinician-facing read of a Patient's record (issue #46). Same
// `/patients/{patientId}/entries` endpoint the Patient's own timeline uses —
// access is decided per-request by the backend (`_authorize_entry_access` /
// Phase 3 `accessible_entries`), not by anything this screen does. A Patient
// this Clinician has no consent for reads **identically** to a Patient who
// does not exist: both are a 404 from the same call, rendered by the same
// `notFound` branch below with no distinguishing text
// (.claude/rules/clinical-safety.md: a 403 would confirm the record exists).
const ENTRY_ICONS: Record<EntryType, typeof DiagnosisIcon> = {
  DIAGNOSIS: DiagnosisIcon,
  PRESCRIPTION: PrescriptionIcon,
  LAB_REPORT: FlaskIcon,
  PROCEDURE: ProcedureIcon,
  CLINICAL_NOTE: ClinicalNoteIcon,
};

const LIMIT = 20;
const ALL_TYPES = "ALL";

type LoadState =
  | { status: "loading" }
  | { status: "notFound" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      items: EntrySummary[];
      nextCursor: string | null;
      loadingMore: boolean;
      loadMoreError: string | null;
    };

function entriesQuery(entryType: EntryType | "", cursor?: string): string {
  const params = new URLSearchParams({ limit: String(LIMIT) });
  if (entryType) params.set("entryType", entryType);
  if (cursor) params.set("cursor", cursor);
  return params.toString();
}

function groupByDate(items: EntrySummary[]): Array<{ dateKey: string; date: Date; rows: EntrySummary[] }> {
  const groups: Array<{ dateKey: string; date: Date; rows: EntrySummary[] }> = [];
  for (const item of items) {
    const date = new Date(item.occurredAt);
    const dateKey = date.toDateString();
    const last = groups[groups.length - 1];
    if (last && last.dateKey === dateKey) {
      last.rows.push(item);
    } else {
      groups.push({ dateKey, date, rows: [item] });
    }
  }
  return groups;
}

export default function ClinicianPatientRecordsPage({
  params,
}: {
  params: Promise<{ patientId: string }>;
}) {
  const { patientId } = use(params);
  const t = useTranslations("clinicianRecords");
  const tTimeline = useTranslations("timeline");
  const errorMessage = useApiErrorMessage();
  const router = useRouter();

  const [typeFilter, setTypeFilter] = useState<EntryType | "">("");
  const [retryToken, setRetryToken] = useState(0);
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (active) setState({ status: "loading" });
    });
    api
      .get<Page<EntrySummary>>(`/patients/${patientId}/entries?${entriesQuery(typeFilter)}`)
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
        // Consent-denied and "no such patient" are the same 404 from the
        // backend — rendered as the same notFound state, deliberately with
        // no branch that distinguishes them.
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
  }, [patientId, typeFilter, retryToken]);

  function loadMore() {
    if (state.status !== "ready" || !state.nextCursor) return;
    const cursor = state.nextCursor;
    setState({ ...state, loadingMore: true, loadMoreError: null });
    api
      .get<Page<EntrySummary>>(`/patients/${patientId}/entries?${entriesQuery(typeFilter, cursor)}`)
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
    <section className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </div>

      <div className="max-w-xs space-y-1.5">
        <Label htmlFor="clinician-entry-type-filter">{tTimeline("filter.label")}</Label>
        <Select
          id="clinician-entry-type-filter"
          value={typeFilter || ALL_TYPES}
          onValueChange={(value) => setTypeFilter(value === ALL_TYPES ? "" : (value as EntryType))}
          placeholder={tTimeline("filter.label")}
          options={[
            { value: ALL_TYPES, label: tTimeline("filter.all") },
            ...ENTRY_TYPES.map((type) => ({ value: type, label: tTimeline(`entryTypes.${type}`) })),
          ]}
        />
      </div>

      {state.status === "loading" && <p className="text-sm text-muted">{t("loading")}</p>}

      {state.status === "notFound" && (
        <Callout tone="info" iconLabel={t("notFound.title")}>
          {t("notFound.body")}
        </Callout>
      )}

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

      {state.status === "ready" && state.items.length === 0 && (
        <Callout tone="info" iconLabel={t("empty.title")}>
          <span className="block font-medium text-foreground">{t("empty.title")}</span>
          <span>{t("empty.body")}</span>
        </Callout>
      )}

      {state.status === "ready" && state.items.length > 0 && (
        <div className="space-y-6">
          {groupByDate(state.items).map((group) => (
            <div key={group.dateKey} className="space-y-2">
              <h2 className="text-sm font-semibold text-muted">{formatDate(group.date)}</h2>
              <ul className="space-y-2">
                {group.rows.map((entry) => (
                  <EntryRow key={entry.id} entry={entry} patientId={patientId} />
                ))}
              </ul>
            </div>
          ))}

          {state.loadMoreError && (
            <Callout tone="error" iconLabel={t("error.title")}>
              {state.loadMoreError}
            </Callout>
          )}

          {state.nextCursor && (
            <Button variant="secondary" loading={state.loadingMore} onClick={loadMore} className="w-full sm:w-auto">
              {state.loadingMore ? t("loadingMore") : t("loadMore")}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}

function EntryRow({ entry, patientId }: { entry: EntrySummary; patientId: string }) {
  const t = useTranslations("timeline");
  const Icon = ENTRY_ICONS[entry.entryType];

  return (
    <li>
      <Link
        href={`/patients/${patientId}/records/${entry.id}`}
        className="flex items-start gap-3 rounded-md border border-border bg-surface px-4 py-3 outline-none hover:bg-surface-raised focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
      >
        <Icon className="mt-0.5 size-5 shrink-0 text-muted" />
        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-xs font-medium text-muted">{t(`entryTypes.${entry.entryType}`)}</span>
            {entry.isCritical && (
              <span className="inline-flex items-center gap-1 rounded-full border border-critical-border bg-critical-surface px-2 py-0.5 text-xs font-medium text-critical">
                <AlertTriangleIcon className="size-3.5" />
                {t("critical")}
              </span>
            )}
          </div>
          <p className="truncate text-sm text-foreground">
            {entry.summary ? <ClinicalText>{entry.summary}</ClinicalText> : "—"}
          </p>
        </div>
      </Link>
    </li>
  );
}
