"use client";

import { useId, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { TriangleAlertIcon } from "lucide-react";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Link, useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api";
import type { Me } from "@/lib/auth";
import { useApiErrorMessage } from "@/lib/errors";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Seeded dev accounts (seed/scripts/build.py `_mark_demo_logins`,
// `build_providers` and `build_administrator`, DEV_PASSWORD in
// seed/scripts/common.py). Real rows from the committed seed dataset — never
// invented — so the buttons below only ever fill the form; the actual login
// still goes through normal validation and `/auth/login`.
const DEMO_PASSWORD = "Pulse@demo1";
const DEMO_ACCOUNTS = [
  { role: "Patient (EN)", email: "demo.patient.en@example.com" },
  { role: "Patient (HI)", email: "demo.patient.hi@example.com" },
  { role: "Provider staff", email: "staff000@example.com" },
  { role: "Clinician", email: "clinician0@example.com" },
  { role: "Administrator", email: "admin0@example.com" },
] as const;

export default function LoginPage() {
  const t = useTranslations("auth");
  const errorMessage = useApiErrorMessage();
  const router = useRouter();

  const emailId = useId();
  const emailErrorId = useId();
  const passwordId = useId();
  const passwordErrorId = useId();
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);

    const next: Record<string, string> = {};
    if (!email) next.email = t("validation.emailRequired");
    else if (!EMAIL_RE.test(email)) next.email = t("validation.emailInvalid");
    if (!password) next.password = t("validation.passwordRequired");
    setErrors(next);
    if (Object.keys(next).length > 0) {
      (next.email ? emailRef : passwordRef).current?.focus();
      return;
    }

    setSubmitting(true);
    try {
      // Session cookie is set by the response; nothing to read from the body.
      await api.post("/auth/login", { email, password });
      // Every non-Patient role has no Patient profile to land on
      // (/profile calls /patients/me, which only exists for Patients).
      // Administrators go to the admin dashboard (ADR-0007); Clinicians and
      // Provider staff go to the patient-lookup screen (docs/demo-script.md
      // — they navigate to one Consent-scoped Patient at a time). Only
      // Patient keeps landing on /profile.
      const me = await api.get<Me>("/auth/me");
      const destination =
        me.role === "ADMINISTRATOR"
          ? "/admin"
          : me.role === "CLINICIAN" || me.role === "PROVIDER_STAFF"
            ? "/clinician"
            : "/profile";
      router.push(destination);
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  function fillDemo(account: (typeof DEMO_ACCOUNTS)[number]) {
    setEmail(account.email);
    setPassword(DEMO_PASSWORD);
    setErrors({});
    setFormError(null);
  }

  return (
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 mx-auto grid max-w-sm gap-6 place-items-center py-6 duration-300 motion-reduce:animate-none sm:py-12">
      <Card className="w-full">
        <CardHeader className="text-center">
          {/* CardTitle renders a <div>; the accessible-heading role here matters
              (e2e selects by role), so this is a plain <h1> with matching type
              styles rather than <CardTitle>. */}
          <h1 className="text-2xl leading-snug font-semibold">{t("login.title")}</h1>
        </CardHeader>
        <CardContent className="space-y-4">
          {formError && (
            <Alert variant="destructive">
              <TriangleAlertIcon />
              <AlertTitle>{formError}</AlertTitle>
            </Alert>
          )}

          <form onSubmit={onSubmit} noValidate className="space-y-4">
            <Field data-invalid={!!errors.email || undefined}>
              <FieldLabel htmlFor={emailId}>{t("fields.email")}</FieldLabel>
              <Input
                ref={emailRef}
                id={emailId}
                type="email"
                autoComplete="email"
                inputMode="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? emailErrorId : undefined}
              />
              {errors.email && <FieldError id={emailErrorId}>{errors.email}</FieldError>}
            </Field>

            <Field data-invalid={!!errors.password || undefined}>
              <FieldLabel htmlFor={passwordId}>{t("fields.password")}</FieldLabel>
              <Input
                ref={passwordRef}
                id={passwordId}
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? passwordErrorId : undefined}
              />
              {errors.password && <FieldError id={passwordErrorId}>{errors.password}</FieldError>}
            </Field>

            <Button type="submit" disabled={submitting} aria-busy={submitting} className="h-11 w-full">
              {submitting && <Spinner />}
              {t("login.submit")}
            </Button>
          </form>
        </CardContent>
        <CardFooter>
          <CardDescription>
            {t("login.noAccount")}{" "}
            <Link href="/register" className="font-medium text-primary underline-offset-4 hover:underline">
              {t("login.registerLink")}
            </Link>
          </CardDescription>
        </CardFooter>
      </Card>

      {/* Demo affordance only — deliberately a separate, secondary card so it
          never reads as part of production auth. Buttons only prefill the
          real form's fields; submission still goes through normal validation
          and `/auth/login`, never bypassed. */}
      <Card className="w-full border-dashed">
        <CardHeader>
          <CardTitle className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            Demo credentials
          </CardTitle>
          <CardDescription>
            Seeded accounts from the demo dataset — password is the same for all.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-2">
          {DEMO_ACCOUNTS.map((account) => (
            <Button
              key={account.email}
              type="button"
              variant="outline"
              className="h-auto min-h-11 w-full min-w-0 flex-col items-start gap-0 py-1.5 text-left"
              onClick={() => fillDemo(account)}
            >
              <span className="text-xs font-semibold text-foreground">{account.role}</span>
              <span className="w-full truncate text-[11px] font-normal text-muted-foreground">
                {account.email}
              </span>
            </Button>
          ))}
        </CardContent>
      </Card>
    </section>
  );
}
