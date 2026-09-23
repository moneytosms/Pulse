"use client";

import { use, useEffect, useId, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslations } from "next-intl";
import {
  ActivityIcon,
  ChevronRightIcon,
  FlaskConicalIcon,
  NotebookPenIcon,
  PillIcon,
  StethoscopeIcon,
  SyringeIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ClinicalText } from "@/components/ClinicalText";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/auth";
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
// A Clinician additionally gets the break-glass form under that 404: a
// justified, audited, 60-minute emergency grant that notifies the Patient.
const ENTRY_ICONS: Record<EntryType, typeof StethoscopeIcon> = {
  DIAGNOSIS: StethoscopeIcon,
  PRESCRIPTION: PillIcon,
  LAB_REPORT: FlaskConicalIcon,
  PROCEDURE: SyringeIcon,
  CLINICAL_NOTE: NotebookPenIcon,
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
  const filterId = useId();

  const [typeFilter, setTypeFilter] = useState<EntryType | "">("");
  const [retryToken, setRetryToken] = useState(0);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [role, setRole] = useState<Me["role"] | null>(null);

  useEffect(() => {
    api
      .get<Me>("/auth/me")
      .then((me) => setRole(me.role))
      .catch(() => setRole(null));
  }, []);

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
    <section className="space-y-8 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-1 motion-safe:duration-300">
      <div className="space-y-1">
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-pretty text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <div className="max-w-xs space-y-1.5">
        <Label htmlFor={filterId}>{tTimeline("filter.label")}</Label>
        <Select
          value={typeFilter || ALL_TYPES}
          onValueChange={(value) => setTypeFilter(value === ALL_TYPES ? "" : (value as EntryType))}
        >
          <SelectTrigger id={filterId} className="w-full">
            <SelectValue placeholder={tTimeline("filter.label")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_TYPES}>{tTimeline("filter.all")}</SelectItem>
            {ENTRY_TYPES.map((type) => (
              <SelectItem key={type} value={type}>
                {tTimeline(`entryTypes.${type}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {state.status === "loading" && (
        <div className="space-y-2">
          <span className="sr-only">{t("loading")}</span>
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      )}

      {state.status === "notFound" && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <TriangleAlertIcon />
            </EmptyMedia>
            <EmptyTitle>{t("notFound.title")}</EmptyTitle>
            <EmptyDescription>{t("notFound.body")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}

      {state.status === "notFound" && role === "CLINICIAN" && (
        <BreakGlassForm patientId={patientId} onGranted={() => setRetryToken((n) => n + 1)} />
      )}

      {state.status === "error" && (
        <div className="space-y-3">
          <Alert variant="destructive">
            <TriangleAlertIcon />
            <AlertTitle>{t("error.title")}</AlertTitle>
            <AlertDescription>{state.message}</AlertDescription>
          </Alert>
          <Button variant="outline" onClick={() => setRetryToken((n) => n + 1)}>
            {t("error.retry")}
          </Button>
        </div>
      )}

      {state.status === "ready" && state.items.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ActivityIcon />
            </EmptyMedia>
            <EmptyTitle>{t("empty.title")}</EmptyTitle>
            <EmptyDescription>{t("empty.body")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}

      {state.status === "ready" && state.items.length > 0 && (
        <div className="space-y-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{tTimeline("detail.fields.occurredAt")}</TableHead>
                <TableHead>{tTimeline("filter.label")}</TableHead>
                <TableHead>{t("title")}</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {state.items.map((entry) => (
                <EntryRow key={entry.id} entry={entry} patientId={patientId} />
              ))}
            </TableBody>
          </Table>

          {state.loadMoreError && (
            <Alert variant="destructive">
              <TriangleAlertIcon />
              <AlertTitle>{t("error.title")}</AlertTitle>
              <AlertDescription>{state.loadMoreError}</AlertDescription>
            </Alert>
          )}

          {state.nextCursor && (
            <Button
              variant="outline"
              disabled={state.loadingMore}
              aria-busy={state.loadingMore}
              onClick={loadMore}
              className="w-full sm:w-auto"
            >
              {state.loadingMore && <Spinner />}
              {state.loadingMore ? t("loadingMore") : t("loadMore")}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}

function BreakGlassForm({ patientId, onGranted }: { patientId: string; onGranted: () => void }) {
  const t = useTranslations("clinicianRecords.breakGlass");
  const errorMessage = useApiErrorMessage();
  const [justification, setJustification] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const fieldId = useId();
  const errorId = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!justification.trim()) {
      setError(t("required"));
      textareaRef.current?.focus();
      return;
    }
    setSubmitting(true);
    api
      .post(`/patients/${patientId}/break-glass`, { justification: justification.trim() })
      .then(onGranted)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setSubmitting(false));
  }

  return (
    <Card className="max-w-lg border-critical-border">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TriangleAlertIcon className="size-5 text-critical" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("body")}</p>
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <Field data-invalid={error ? true : undefined}>
            <FieldLabel htmlFor={fieldId}>{t("justification")}</FieldLabel>
            <Textarea
              ref={textareaRef}
              id={fieldId}
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              rows={3}
              maxLength={2000}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? errorId : undefined}
            />
            {error && <FieldError id={errorId}>{error}</FieldError>}
          </Field>
          <Button type="submit" variant="outline" disabled={submitting} aria-busy={submitting}>
            {submitting && <Spinner />}
            {t("submit")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function EntryRow({ entry, patientId }: { entry: EntrySummary; patientId: string }) {
  const t = useTranslations("timeline");
  const router = useRouter();
  const Icon = ENTRY_ICONS[entry.entryType];
  const href = `/patients/${patientId}/records/${entry.id}` as const;

  return (
    <TableRow
      tabIndex={0}
      role="link"
      onClick={() => router.push(href)}
      onKeyDown={(e) => {
        if (e.key === "Enter") router.push(href);
      }}
      className="cursor-pointer outline-none focus-visible:bg-muted/50 focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      <TableCell className="tabular-nums text-muted-foreground">{formatDate(entry.occurredAt)}</TableCell>
      <TableCell>
        <span className="flex items-center gap-1.5">
          <Icon className="size-4 shrink-0 text-muted-foreground" />
          {t(`entryTypes.${entry.entryType}`)}
          {entry.isCritical && (
            <Badge variant="outline" className="gap-1 border-critical-border bg-critical-surface text-critical">
              <TriangleAlertIcon />
              {t("critical")}
            </Badge>
          )}
        </span>
      </TableCell>
      <TableCell className="whitespace-normal">
        <Link
          href={href}
          onClick={(e) => e.stopPropagation()}
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          {entry.summary ? <ClinicalText>{entry.summary}</ClinicalText> : "—"}
        </Link>
      </TableCell>
      <TableCell>
        <ChevronRightIcon className="size-4 text-muted-foreground" />
      </TableCell>
    </TableRow>
  );
}
