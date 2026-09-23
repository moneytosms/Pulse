"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { CircleAlertIcon, CircleCheckIcon, InfoIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";

type State = "checking" | "success" | "expired" | "failed" | "missing";

function Verify() {
  const t = useTranslations("auth");
  const params = useSearchParams();
  const challengeId = params.get("challenge");
  const token = params.get("token");

  const [state, setState] = useState<State>(challengeId && token ? "checking" : "missing");
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current || !challengeId || !token) return;
    ran.current = true;
    api
      .post("/auth/verify", { challengeId, token })
      .then(() => setState("success"))
      .catch((err) => {
        if (err instanceof ApiError && err.code === "VERIFICATION_TOKEN_EXPIRED") {
          setState("expired");
        } else {
          setState("failed");
        }
      });
  }, [challengeId, token]);

  const body: Record<
    State,
    { variant: "default" | "destructive"; icon: typeof InfoIcon; text: string }
  > = {
    checking: { variant: "default", icon: InfoIcon, text: t("verify.checking") },
    success: { variant: "default", icon: CircleCheckIcon, text: t("verify.success") },
    expired: { variant: "destructive", icon: CircleAlertIcon, text: t("verify.expired") },
    failed: { variant: "destructive", icon: CircleAlertIcon, text: t("verify.failed") },
    missing: { variant: "destructive", icon: CircleAlertIcon, text: t("verify.missingParams") },
  };
  const current = body[state];
  const Icon = current.icon;

  return (
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 mx-auto max-w-sm space-y-6 duration-300 motion-reduce:animate-none">
      <h1 className="text-2xl font-bold text-foreground">{t("verify.title")}</h1>

      <Alert
        variant={current.variant}
        className={state === "success" ? "border-consent-active/40 text-consent-active" : undefined}
      >
        <Icon />
        <AlertDescription className={state === "success" ? "text-consent-active" : undefined}>
          {current.text}
        </AlertDescription>
      </Alert>

      {state === "success" && (
        <Button asChild className="h-11 w-full">
          <Link href="/login">{t("verify.continue")}</Link>
        </Button>
      )}
      {(state === "expired" || state === "missing") && (
        <Button asChild variant="outline" className="h-11 w-full">
          <Link href="/verify-pending">{t("verifyPending.resend")}</Link>
        </Button>
      )}
    </section>
  );
}

export default function VerifyPage() {
  return (
    <Suspense>
      <Verify />
    </Suspense>
  );
}
