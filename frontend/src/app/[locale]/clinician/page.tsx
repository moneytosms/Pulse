"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslations } from "next-intl";
import { TriangleAlertIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/auth";
import type { ConsentedPatient } from "@/lib/consent";
import { formatDate } from "@/lib/format";
import type { Page } from "@/lib/records";

// Clinician / Provider-staff landing page (login previously sent every
// non-Administrator role to /profile, which is Patient-only and 403s —
// this is the gap that fix closes). Per docs/demo.md, a Clinician
// has no dashboard: they navigate directly to a specific
// /patients/{patientId}/records URL, because a Consent grant is scoped to
// one Patient at a time. This screen is only that navigation step made
// explicit instead of left to a manually-typed URL.
type GateState =
  | { status: "loading" }
  | { status: "denied" }
  | { status: "error" }
  | { status: "ready"; role: "CLINICIAN" | "PROVIDER_STAFF" };

// A Clinician's list of Patients who granted them access — never cached
// (clinical-safety.md: "never cache a permission decision"), so this is a
// plain fetch on mount, not a query cache with staleTime.
type PatientsState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: ConsentedPatient[]; nextCursor: string | null; loadingMore: boolean; error: string | null };

export default function ClinicianHomePage() {
  const t = useTranslations("clinicianHome");
  const router = useRouter();
  const [gate, setGate] = useState<GateState>({ status: "loading" });
  const [patients, setPatients] = useState<PatientsState>({ status: "loading" });
  const [patientId, setPatientId] = useState("");
  const [patientsRetry, setPatientsRetry] = useState(0);
  const paginationRequest = useRef<AbortController | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fieldId = useId();
  const errorId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    api
      .get<Me>("/auth/me")
      .then((me) => {
        if (!active) return;
        if (me.role === "CLINICIAN" || me.role === "PROVIDER_STAFF") {
          setGate({ status: "ready", role: me.role });
        } else {
          setGate({ status: "denied" });
        }
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && (err.status === 401 || err.code === "SESSION_EXPIRED")) {
          router.replace("/login");
          return;
        }
        setGate({ status: "error" });
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (gate.status !== "ready" || gate.role !== "CLINICIAN") return;
    let active = true;
    Promise.resolve().then(() => { if (active) setPatients({ status: "loading" }); });
    api
      .get<Page<ConsentedPatient>>("/consents/granted-to-me")
      .then((page) => {
        if (active) setPatients({ status: "ready", items: page.items, nextCursor: page.nextCursor, loadingMore: false, error: null });
      })
      .catch(() => {
        if (active) setPatients({ status: "error" });
      });
    return () => {
      paginationRequest.current?.abort();
      active = false;
    };
  }, [gate, patientsRetry]);

  async function loadMorePatients() {
    if (patients.status !== "ready" || !patients.nextCursor || patients.loadingMore) return;
    paginationRequest.current?.abort();
    const controller = new AbortController();
    paginationRequest.current = controller;
    const cursor = patients.nextCursor;
    setPatients({ ...patients, loadingMore: true, error: null });
    try {
      const page = await api.get<Page<ConsentedPatient>>(`/consents/granted-to-me?cursor=${encodeURIComponent(cursor)}`, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setPatients(prev => prev.status === "ready" ? { status: "ready", items: [...prev.items, ...page.items], nextCursor: page.nextCursor, loadingMore: false, error: null } : prev);
    } catch {
      if (controller.signal.aborted) return;
      setPatients(prev => prev.status === "ready" ? { ...prev, loadingMore: false, error: t("patients.error") } : prev);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const trimmed = patientId.trim();
    if (!trimmed) {
      setError(t("form.validation.required"));
      inputRef.current?.focus();
      return;
    }
    router.push(`/patients/${trimmed}/records`);
  }

  if (gate.status === "loading") {
    return <p className="text-sm text-muted-foreground">{t("loading")}</p>;
  }
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
        <AlertDescription>{t("gate.error")}</AlertDescription>
      </Alert>
    );
  }

  return (
    <section className="mx-auto max-w-lg space-y-8 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-1 motion-safe:duration-300">
      <div className="space-y-1">
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-pretty text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      {gate.role === "CLINICIAN" && (
        <Card>
          <CardHeader>
            <CardTitle>{t("patients.title")}</CardTitle>
          </CardHeader>
          <CardContent>
            {patients.status === "loading" && (
              <p className="text-sm text-muted-foreground">{t("loading")}</p>
            )}
            {patients.status === "error" && (
              <div className="space-y-3"><Alert variant="destructive">
                <TriangleAlertIcon />
                <AlertDescription>{t("patients.error")}</AlertDescription>
              </Alert><Button variant="outline" onClick={() => setPatientsRetry(n => n + 1)}>{t("patients.retry")}</Button></div>
            )}
            {patients.status === "ready" && patients.items.length === 0 && (
              <p className="text-sm text-muted-foreground">{t("patients.empty")}</p>
            )}
            {patients.status === "ready" && patients.items.length > 0 && (
              <ul className="space-y-2">
                {patients.items.map((patient) => (
                  <li key={patient.patientId}>
                    <Link
                      href={`/patients/${patient.patientId}/records`}
                      className="block rounded-md border p-3 hover:bg-accent"
                    >
                      <span className="font-medium">{patient.fullName}</span>
                      <span className="block text-xs text-muted-foreground">
                        {patient.patientId}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {t("patients.until", { date: formatDate(patient.expiresAt) })}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {patients.status === "ready" && patients.error && <Alert variant="destructive"><AlertDescription>{patients.error}</AlertDescription></Alert>}
            {patients.status === "ready" && patients.nextCursor && <Button variant="outline" disabled={patients.loadingMore} aria-busy={patients.loadingMore} onClick={loadMorePatients}>{t("patients.loadMore")}</Button>}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t("form.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} noValidate className="space-y-4">
            <Field data-invalid={error ? true : undefined}>
              <FieldLabel htmlFor={fieldId}>{t("form.fields.patientId")}</FieldLabel>
              <Input
                ref={inputRef}
                id={fieldId}
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
                placeholder={t("form.fields.patientIdPlaceholder")}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? errorId : undefined}
              />
              {error && <FieldError id={errorId}>{error}</FieldError>}
            </Field>
            <Button type="submit" className="w-full">
              {t("form.submit")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </section>
  );
}
