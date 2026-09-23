"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { TriangleAlertIcon } from "lucide-react";
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Link, useRouter } from "@/i18n/navigation";
import type { DuplicateReviewCandidate, MergeRecord, MergeResult } from "@/lib/admin";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/auth";
import { useApiErrorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/format";

// Duplicate review UI (issue #55). Renders `AdminPatientIdentity` fields
// only — `id`, `fullName`, `dateOfBirth`, `phone`, `claimed`, `entryCount` —
// never an entry's clinical content. That guarantee is structural, not a
// rendering choice: `DuplicateReviewCandidate`/`AdminPatientIdentity`
// (`lib/admin.ts`, mirroring `backend/app/modules/admin/schemas.py`) have no
// field capable of holding clinical content, and this screen fetches nothing
// else about either patient.
//
// Reversal reads `GET /admin/merges` (every unreversed merge, by any
// admin, in any session), so a merge stays reversible after a reload.
// Names only — identity, never clinical content.
type GateState = { status: "loading" } | { status: "denied" } | { status: "error"; message: string } | { status: "ready" };

type QueueState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; items: DuplicateReviewCandidate[] };

type RowBusy = "merge" | "notDuplicate" | null;

export default function DuplicateReviewPage() {
  const t = useTranslations("admin");
  const errorMessage = useApiErrorMessage();
  const router = useRouter();

  const [gate, setGate] = useState<GateState>({ status: "loading" });
  const [queue, setQueue] = useState<QueueState>({ status: "loading" });
  const [busyId, setBusyId] = useState<string | null>(null);
  const [busyKind, setBusyKind] = useState<RowBusy>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [merges, setMerges] = useState<MergeRecord[]>([]);
  const [reversingId, setReversingId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .get<Me>("/auth/me")
      .then((me) => {
        if (!active) return;
        if (me.role !== "ADMINISTRATOR") {
          setGate({ status: "denied" });
          return;
        }
        setGate({ status: "ready" });
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && (err.status === 401 || err.code === "SESSION_EXPIRED")) {
          router.replace("/login");
          return;
        }
        setGate({ status: "error", message: t("gate.error") });
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [retryToken] = useState(0);

  useEffect(() => {
    if (gate.status !== "ready") return;
    let active = true;
    Promise.resolve().then(() => {
      if (active) setQueue({ status: "loading" });
    });
    api
      .get<DuplicateReviewCandidate[]>("/admin/duplicate-review")
      .then((items) => {
        if (active) setQueue({ status: "ready", items });
      })
      .catch((err) => {
        if (active) setQueue({ status: "error", message: errorMessage(err) });
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gate.status, retryToken]);

  function loadMerges() {
    api
      .get<MergeRecord[]>("/admin/merges")
      .then(setMerges)
      .catch((err) => setActionError(errorMessage(err)));
  }

  useEffect(() => {
    if (gate.status === "ready") loadMerges();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gate.status]);

  function markNotDuplicate(candidate: DuplicateReviewCandidate) {
    setBusyId(candidate.id);
    setBusyKind("notDuplicate");
    setActionError(null);
    api
      .post("/admin/duplicate-review/not-duplicate", {
        patientIdA: candidate.patientA.id,
        patientIdB: candidate.patientB.id,
      })
      .then(() => {
        setQueue((prev) =>
          prev.status === "ready"
            ? { ...prev, items: prev.items.filter((c) => c.id !== candidate.id) }
            : prev,
        );
      })
      .catch((err) => setActionError(errorMessage(err)))
      .finally(() => {
        setBusyId(null);
        setBusyKind(null);
      });
  }

  function merge(candidate: DuplicateReviewCandidate) {
    // The candidate with more entries wins by default — a reasonable default
    // absent any ticket guidance on which side should be the winner; the
    // admin can still tell the two apart before confirming since both
    // identities are shown in full.
    const winner =
      candidate.patientA.entryCount >= candidate.patientB.entryCount
        ? candidate.patientA
        : candidate.patientB;
    const loser = winner === candidate.patientA ? candidate.patientB : candidate.patientA;

    setBusyId(candidate.id);
    setBusyKind("merge");
    setActionError(null);
    api
      .post<MergeResult>("/admin/duplicate-review/merge", {
        winnerPatientId: winner.id,
        loserPatientId: loser.id,
      })
      .then(() => {
        loadMerges();
        setQueue((prev) =>
          prev.status === "ready"
            ? { ...prev, items: prev.items.filter((c) => c.id !== candidate.id) }
            : prev,
        );
      })
      .catch((err) => setActionError(errorMessage(err)))
      .finally(() => {
        setBusyId(null);
        setBusyKind(null);
      });
  }

  function reverseMerge(mergeId: string) {
    setReversingId(mergeId);
    setActionError(null);
    api
      .post<MergeResult>(`/admin/merges/${mergeId}/reverse`)
      .then((result) => {
        setMerges((prev) =>
          prev.map((m) => (m.id === result.id ? { ...m, reversedAt: result.reversedAt } : m)),
        );
      })
      .catch((err) => setActionError(errorMessage(err)))
      .finally(() => setReversingId(null));
  }

  if (gate.status === "loading") return <p className="text-sm text-muted-foreground">{t("loading")}</p>;
  if (gate.status === "denied") {
    return (
      <Alert variant="destructive">
        <TriangleAlertIcon />
        <AlertTitle>{t("gate.title")}</AlertTitle>
        <AlertDescription>{t("gate.denied")}</AlertDescription>
      </Alert>
    );
  }
  if (gate.status === "error") {
    return (
      <Alert variant="destructive">
        <TriangleAlertIcon />
        <AlertTitle>{t("gate.title")}</AlertTitle>
        <AlertDescription>{gate.message}</AlertDescription>
      </Alert>
    );
  }

  return (
    <section className="space-y-8 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-1 motion-safe:duration-300">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/admin">{t("title")}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{t("duplicateReview.title")}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="space-y-1">
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
          {t("duplicateReview.title")}
        </h1>
        <p className="text-pretty text-sm text-muted-foreground">{t("duplicateReview.description")}</p>
      </div>

      {actionError && (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>{t("duplicateReview.actionErrorTitle")}</AlertTitle>
          <AlertDescription>{actionError}</AlertDescription>
        </Alert>
      )}

      {queue.status === "loading" && <p className="text-sm text-muted-foreground">{t("loading")}</p>}

      {queue.status === "error" && (
        <Alert variant="destructive">
          <TriangleAlertIcon />
          <AlertTitle>{t("duplicateReview.actionErrorTitle")}</AlertTitle>
          <AlertDescription>{queue.message}</AlertDescription>
        </Alert>
      )}

      {queue.status === "ready" && queue.items.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <TriangleAlertIcon />
            </EmptyMedia>
            <EmptyTitle>{t("duplicateReview.emptyTitle")}</EmptyTitle>
            <EmptyDescription>{t("duplicateReview.empty")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}

      {queue.status === "ready" &&
        queue.items.map((candidate) => (
          <Card key={candidate.id}>
            <CardHeader className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">
                {t("duplicateReview.candidateTitle")}
              </CardTitle>
              <Badge variant="outline">
                <span className="tabular-nums">{t("duplicateReview.score", { score: candidate.score.toFixed(2) })}</span>
              </Badge>
            </CardHeader>
            <CardContent className="space-y-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead></TableHead>
                    <TableHead>{t("duplicateReview.fields.dateOfBirth")}</TableHead>
                    <TableHead>{t("duplicateReview.fields.phone")}</TableHead>
                    <TableHead>{t("duplicateReview.fields.claimed")}</TableHead>
                    <TableHead>{t("duplicateReview.fields.entryCount")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[candidate.patientA, candidate.patientB].map((p, idx) => (
                    <TableRow key={p.id}>
                      <TableCell className="font-medium">
                        <span className="block text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                          {t("duplicateReview.candidateLabel", { n: idx + 1 })}
                        </span>
                        {p.fullName}
                      </TableCell>
                      <TableCell className="tabular-nums">{formatDate(p.dateOfBirth) || "—"}</TableCell>
                      <TableCell>{p.phone ?? "—"}</TableCell>
                      <TableCell>
                        {p.claimed ? t("duplicateReview.claimedTrue") : t("duplicateReview.claimedFalse")}
                      </TableCell>
                      <TableCell className="tabular-nums">{p.entryCount}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              <div className="flex flex-wrap gap-3">
                <Button
                  disabled={busyId !== null}
                  aria-busy={busyId === candidate.id && busyKind === "merge"}
                  onClick={() => merge(candidate)}
                >
                  {busyId === candidate.id && busyKind === "merge" && <Spinner />}
                  {t("duplicateReview.mergeCta")}
                </Button>
                <Button
                  variant="outline"
                  disabled={busyId !== null}
                  aria-busy={busyId === candidate.id && busyKind === "notDuplicate"}
                  onClick={() => markNotDuplicate(candidate)}
                >
                  {busyId === candidate.id && busyKind === "notDuplicate" && <Spinner />}
                  {t("duplicateReview.notDuplicateCta")}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}

      {merges.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("duplicateReview.recentMerges.title")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-muted-foreground">{t("duplicateReview.recentMerges.hint")}</p>
            <Table>
              <TableBody>
                {merges.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>
                      {t("duplicateReview.recentMerges.pair", { winner: m.winnerName, loser: m.loserName })}
                      <span className="ml-2 tabular-nums text-muted-foreground">{formatDate(m.occurredAt)}</span>
                      {m.reversedAt && (
                        <Badge variant="outline" className="ml-2">
                          {t("duplicateReview.recentMerges.reversed")}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {!m.reversedAt && (
                        <Button
                          variant="outline"
                          disabled={reversingId !== null}
                          aria-busy={reversingId === m.id}
                          onClick={() => reverseMerge(m.id)}
                        >
                          {reversingId === m.id && <Spinner />}
                          {t("duplicateReview.recentMerges.reverseCta")}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
