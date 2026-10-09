"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { BreakGlassBanner } from "@/components/BreakGlassBanner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { SelectFilter } from "@/components/SelectFilter";
import type { EntryProvider } from "@/lib/generated/api";
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
import { ClinicalText } from "@/components/ClinicalText";
import {
  ChevronRightIcon,
  ClockIcon,
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
import {
  ENTRY_TYPES,
  type EntrySummary,
  type EntryType,
  type Page,
} from "@/lib/records";

// One icon per entry-type renderer, paired with the localized type label —
// never colour alone (.claude/rules/frontend.md).
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

function entriesQuery(
  entryType: EntryType | "",
  filters: { q: string; fromDate: string; toDate: string; providerId: string },
  cursor?: string,
): string {
  const params = new URLSearchParams({ limit: String(LIMIT) });
  if (entryType) params.set("entryType", entryType);
  for (const [key, value] of Object.entries(filters))
    if (value.trim()) params.set(key, value.trim());
  if (cursor) params.set("cursor", cursor);
  return params.toString();
}

/** Group already-sorted (occurredAt desc) rows under their calendar day,
 * preserving order — never re-sorted client-side. */
function groupByDate(
  items: EntrySummary[],
): Array<{ dateKey: string; date: Date; rows: EntrySummary[] }> {
  const groups: Array<{ dateKey: string; date: Date; rows: EntrySummary[] }> =
    [];
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

export default function TimelinePage() {
  const t = useTranslations("timeline");
  const errorMessage = useApiErrorMessage();
  const router = useRouter();
  const filterId = useId();

  const [patientId, setPatientId] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<EntryType | "">("");
  const [filters, setFilters] = useState({
    q: "",
    fromDate: "",
    toDate: "",
    providerId: "",
  });
  const [applied, setApplied] = useState(filters);
  const [filterError, setFilterError] = useState(false);
  const [providers, setProviders] = useState<EntryProvider[]>([]);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const paginationRequest = useRef<AbortController | null>(null);

  // Resolve the current patient id once — the entries endpoint is nested
  // under it (docs/api-conventions.md: entries are meaningless without a
  // patient).
  useEffect(() => {
    if (patientId) return;
    let active = true;
    Promise.resolve().then(() => {
      if (active) setState({ status: "loading" });
    });
    api
      .get<{ id: string }>("/patients/me")
      .then((profile) => {
        if (active) setPatientId(profile.id);
      })
      .catch((err) => {
        if (!active) return;
        if (
          err instanceof ApiError &&
          (err.status === 401 || err.code === "SESSION_EXPIRED")
        ) {
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
  }, [patientId, retryToken]);

  // Fetch (or re-fetch) the first page whenever the patient id, the type
  // filter, or an explicit retry changes. Inlined rather than built from a
  // `useCallback` — `errorMessage` is a fresh function every render, so a
  // memoized wrapper depending on it would itself change identity every
  // render and re-trigger this effect in a loop that never settles.
  useEffect(() => {
    if (!patientId) return;
    let active = true;
    // Deferred one microtask so the reset is a callback, not a direct
    // synchronous setState in the effect body (react-hooks/set-state-in-effect).
    Promise.resolve().then(() => {
      if (active) setState({ status: "loading" });
    });
    api
      .get<Page<EntrySummary>>(
        `/patients/${patientId}/entries?${entriesQuery(typeFilter, applied)}`,
      )
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
        if (
          err instanceof ApiError &&
          (err.status === 401 || err.code === "SESSION_EXPIRED")
        ) {
          router.replace("/login");
          return;
        }
        setState({ status: "error", message: errorMessage(err) });
      });
    return () => {
      paginationRequest.current?.abort();
      active = false;
    };
    // errorMessage / router are stable for the page lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId, typeFilter, applied, retryToken]);

  useEffect(() => {
    if (!patientId) return;
    const controller = new AbortController();
    api
      .get<EntryProvider[]>(`/patients/${patientId}/entry-providers`, {
        signal: controller.signal,
      })
      .then((items) => {
        if (!controller.signal.aborted) {
          setProviders(items);
          setProviderError(null);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) setProviderError(errorMessage(err));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId, retryToken]);

  function loadMore() {
    if (!patientId || state.status !== "ready" || !state.nextCursor) return;
    const cursor = state.nextCursor;
    paginationRequest.current?.abort();
    const controller = new AbortController();
    paginationRequest.current = controller;
    setState({ ...state, loadingMore: true, loadMoreError: null });
    api
      .get<Page<EntrySummary>>(
        `/patients/${patientId}/entries?${entriesQuery(typeFilter, applied, cursor)}`,
        { signal: controller.signal },
      )
      .then((page) => {
        if (controller.signal.aborted) return;
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
        if (controller.signal.aborted) return;
        setState((prev) =>
          prev.status === "ready"
            ? { ...prev, loadingMore: false, loadMoreError: errorMessage(err) }
            : prev,
        );
      });
  }

  return (
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 space-y-8 duration-300 motion-reduce:animate-none">
      {patientId && <BreakGlassBanner patientId={patientId} />}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
            {t("title")}
          </h1>
          <p className="text-pretty text-muted-foreground">{t("subtitle")}</p>
        </div>
      </div>

      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (
            filters.fromDate &&
            filters.toDate &&
            filters.fromDate > filters.toDate
          ) {
            setFilterError(true);
            return;
          }
          paginationRequest.current?.abort();
          setFilterError(false);
          setApplied({ ...filters, q: filters.q.trim() });
        }}
      >
        <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor={`${filterId}-search`}>{t("search.label")}</Label>
            <Input
              id={`${filterId}-search`}
              type="search"
              maxLength={100}
              value={filters.q}
              placeholder={t("search.placeholder")}
              onChange={(e) => setFilters({ ...filters, q: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={filterId}>{t("filter.label")}</Label>
            <Select
              value={typeFilter || ALL_TYPES}
              onValueChange={(value) => {
                paginationRequest.current?.abort();
                setTypeFilter(value === ALL_TYPES ? "" : (value as EntryType));
              }}
            >
              <SelectTrigger
                id={filterId}
                aria-label={t("filter.label")}
                className="w-full"
              >
                <SelectValue placeholder={t("filter.label")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_TYPES}>{t("filter.all")}</SelectItem>
                {ENTRY_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>
                    {t(`entryTypes.${type}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <details className="rounded-lg border px-3 py-2">
          <summary className="cursor-pointer text-sm font-medium">
            {t("search.more")}
          </summary>
          <div className="mt-3 grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={`${filterId}-from`}>{t("search.from")}</Label>
              <Input
                id={`${filterId}-from`}
                type="date"
                value={filters.fromDate}
                onChange={(e) =>
                  setFilters({ ...filters, fromDate: e.target.value })
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`${filterId}-through`}>
                {t("search.through")}
              </Label>
              <Input
                id={`${filterId}-through`}
                type="date"
                value={filters.toDate}
                onChange={(e) =>
                  setFilters({ ...filters, toDate: e.target.value })
                }
              />
            </div>
            <SelectFilter
              label={t("search.provider")}
              value={filters.providerId}
              onChange={(e) =>
                setFilters({ ...filters, providerId: e.target.value })
              }
            >
              <option value="">{t("search.allProviders")}</option>
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </SelectFilter>
            {providerError && (
              <div className="space-y-2">
                <p role="alert" className="text-sm text-destructive">
                  {t("search.providerError")}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setRetryToken((n) => n + 1)}
                >
                  {t("error.retry")}
                </Button>
              </div>
            )}
          </div>
        </details>
        <p className="text-sm text-muted-foreground">{t("search.timezone")}</p>
        {filterError && (
          <p role="alert" className="text-sm text-destructive">
            {t("search.dateOrder")}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit">{t("search.apply")}</Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              const empty = { q: "", fromDate: "", toDate: "", providerId: "" };
              paginationRequest.current?.abort();
              setTypeFilter("");
              setFilters(empty);
              setApplied(empty);
              setFilterError(false);
            }}
          >
            {t("search.reset")}
          </Button>
        </div>
      </form>

      {state.status === "loading" && (
        <div className="space-y-3" role="status" aria-live="polite">
          <p className="sr-only">{t("loading")}</p>
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      )}

      {state.status === "notFound" && (
        <Alert>
          <AlertTitle>{t("title")}</AlertTitle>
          <AlertDescription>{t("notFound")}</AlertDescription>
        </Alert>
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
        <EmptyState
          typeFilter={typeFilter}
          narrowed={Object.values(applied).some(Boolean)}
        />
      )}

      {state.status === "ready" && state.items.length > 0 && (
        <div className="space-y-6">
          {groupByDate(state.items).map((group) => (
            <div key={group.dateKey} className="space-y-2">
              <h2 className="text-sm font-medium tabular-nums text-muted-foreground">
                {formatDate(group.date)}
              </h2>
              <ul className="space-y-2">
                {group.rows.map((entry) => (
                  <EntryRow key={entry.id} entry={entry} />
                ))}
              </ul>
            </div>
          ))}

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

// Distinct from the load-failure Alert above: "no entries" is a clean
// server response with `items: []`, not an error. A type filter narrows the
// message to that type specifically (issue #33 scope).
function EmptyState({
  typeFilter,
  narrowed,
}: {
  typeFilter: EntryType | "";
  narrowed: boolean;
}) {
  const t = useTranslations("timeline");
  const title = narrowed
    ? t("search.emptyTitle")
    : typeFilter
      ? t("emptyFiltered.title", { type: t(`entryTypes.${typeFilter}`) })
      : t("empty.title");
  const body = narrowed
    ? t("search.emptyBody")
    : typeFilter
      ? t("emptyFiltered.body", { type: t(`entryTypes.${typeFilter}`) })
      : t("empty.body");
  return (
    <Empty className="border">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <ClockIcon />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>{body}</EmptyDescription>
      </EmptyHeader>
      <EmptyContent />
    </Empty>
  );
}

function EntryRow({ entry }: { entry: EntrySummary }) {
  const t = useTranslations("timeline");
  const Icon = ENTRY_ICONS[entry.entryType];

  return (
    <li>
      <Link
        href={`/timeline/${entry.id}`}
        className="flex min-h-11 items-center gap-3 rounded-xl border bg-card px-4 py-3 text-sm shadow-sm outline-none transition-colors hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-xs font-medium text-muted-foreground">
              {t(`entryTypes.${entry.entryType}`)}
            </span>
            {entry.isCritical && (
              <Badge
                variant="outline"
                className="gap-1 border-destructive/40 text-destructive"
              >
                <TriangleAlertIcon className="size-3.5" />
                {t("critical")}
              </Badge>
            )}
          </div>
          {entry.providerName && (
            <p className="truncate text-sm text-muted-foreground">
              {entry.providerName}
            </p>
          )}
          <p className="break-words text-sm text-foreground">
            {entry.summary ? <ClinicalText>{entry.summary}</ClinicalText> : "—"}
          </p>
        </div>
        <ChevronRightIcon
          className="size-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
      </Link>
    </li>
  );
}
