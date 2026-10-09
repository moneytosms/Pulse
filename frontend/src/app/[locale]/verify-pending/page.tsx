"use client";

import { Suspense, useId, useState } from "react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { CircleAlertIcon, CircleCheckIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/errors";

function VerifyPending() {
  const t = useTranslations("auth");
  const errorMessage = useApiErrorMessage();
  const initialEmail = useSearchParams().get("email") ?? "";
  const [email, setEmail] = useState(initialEmail);
  const id = useId();
  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  async function resend(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === "sending") return;
    setStatus("sending");
    setError(null);
    try {
      await api.post("/auth/verify/resend", { email: email.trim() });
      setStatus("sent");
    } catch (err) {
      setError(errorMessage(err));
      setStatus("idle");
    }
  }

  return (
    <section className="mx-auto max-w-sm space-y-6">
      <h1 className="text-2xl font-bold">{t("verifyPending.title")}</h1>
      <p className="text-sm text-muted-foreground">
        {initialEmail
          ? t("verifyPending.body", { email: initialEmail })
          : t("verifyPending.enterEmail")}
      </p>
      {status === "sent" && (
        <Alert className="border-consent-active/40 text-consent-active">
          <CircleCheckIcon />
          <AlertDescription>{t("verifyPending.resent")}</AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <CircleAlertIcon />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <form onSubmit={resend} className="space-y-4">
        <Field>
          <FieldLabel htmlFor={id}>{t("fields.email")}</FieldLabel>
          <Input
            id={id}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setStatus("idle");
            }}
            disabled={status === "sending"}
          />
        </Field>
        <Button
          type="submit"
          variant="outline"
          disabled={status === "sending"}
          aria-busy={status === "sending"}
          className="h-11 w-full"
        >
          {status === "sending" && <Spinner />}
          {t("verifyPending.resend")}
        </Button>
      </form>
      <p className="text-sm">
        <Link
          href="/login"
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          {t("verifyPending.backToLogin")}
        </Link>
      </p>
    </section>
  );
}

export default function VerifyPendingPage() {
  return (
    <Suspense>
      <VerifyPending />
    </Suspense>
  );
}
