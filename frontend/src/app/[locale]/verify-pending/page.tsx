"use client";

import { Suspense, useState } from "react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { CircleAlertIcon, CircleCheckIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { useApiErrorMessage } from "@/lib/errors";

function VerifyPending() {
  const t = useTranslations("auth");
  const errorMessage = useApiErrorMessage();
  const email = useSearchParams().get("email") ?? "";

  const [status, setStatus] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  async function resend() {
    if (!email) return;
    setStatus("sending");
    setError(null);
    try {
      await api.post("/auth/verify/resend", { email });
      setStatus("sent");
    } catch (err) {
      setError(errorMessage(err));
      setStatus("idle");
    }
  }

  return (
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 mx-auto max-w-sm space-y-6 duration-300 motion-reduce:animate-none">
      <h1 className="text-2xl font-bold text-foreground">{t("verifyPending.title")}</h1>

      <p className="text-sm text-muted-foreground">
        {email ? t("verifyPending.body", { email }) : t("verifyPending.bodyNoEmail")}
      </p>

      {status === "sent" && (
        <Alert className="border-consent-active/40 text-consent-active">
          <CircleCheckIcon />
          <AlertDescription className="text-consent-active">
            {t("verifyPending.resent")}
          </AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <CircleAlertIcon />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {email && (
        <Button
          variant="outline"
          disabled={status === "sending"}
          aria-busy={status === "sending"}
          onClick={resend}
          className="h-11 w-full"
        >
          {status === "sending" && <Spinner />}
          {t("verifyPending.resend")}
        </Button>
      )}

      <p className="text-sm">
        <Link href="/login" className="font-medium text-primary underline-offset-4 hover:underline">
          {t("verifyPending.backToLogin")}
        </Link>
      </p>
    </section>
  );
}

export default function VerifyPendingPage() {
  // useSearchParams needs a Suspense boundary in the App Router.
  return (
    <Suspense>
      <VerifyPending />
    </Suspense>
  );
}
