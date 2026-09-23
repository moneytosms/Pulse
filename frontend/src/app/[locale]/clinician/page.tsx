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
import { useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/auth";

// Clinician / Provider-staff landing page (login previously sent every
// non-Administrator role to /profile, which is Patient-only and 403s —
// this is the gap that fix closes). Per docs/demo-script.md, a Clinician
// has no dashboard: they navigate directly to a specific
// /patients/{patientId}/records URL, because a Consent grant is scoped to
// one Patient at a time. This screen is only that navigation step made
// explicit instead of left to a manually-typed URL.
type GateState =
  | { status: "loading" }
  | { status: "denied" }
  | { status: "error" }
  | { status: "ready" };

export default function ClinicianHomePage() {
  const t = useTranslations("clinicianHome");
  const router = useRouter();
  const [gate, setGate] = useState<GateState>({ status: "loading" });
  const [patientId, setPatientId] = useState("");
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
        setGate(
          me.role === "CLINICIAN" || me.role === "PROVIDER_STAFF"
            ? { status: "ready" }
            : { status: "denied" },
        );
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
