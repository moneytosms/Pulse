"use client";

import { Suspense, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { CircleAlertIcon, CircleCheckIcon, InfoIcon } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";

type State =
  | "checking"
  | "success"
  | "expired"
  | "failed"
  | "missing"
  | "temporary";

// This browser-only single-flight result survives locale remounts and Strict
// Mode. A one-use verification token must not be submitted twice just to
// translate its outcome. Explicit retry replaces the failed request; no
// clinical data or permission decision is cached.
let verificationRequest: { key: string; promise: Promise<unknown> } | null =
  null;

function Verify() {
  const t = useTranslations("auth");
  const params = useSearchParams();
  const challengeId = params.get("challenge");
  const token = params.get("token");

  const [state, setState] = useState<State>(
    challengeId && token ? "checking" : "missing",
  );
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    let active = true;
    if (!challengeId || !token) {
      Promise.resolve().then(() => {
        if (active) setState("missing");
      });
      return () => {
        active = false;
      };
    }
    const key = JSON.stringify([challengeId, token]);
    Promise.resolve().then(() => {
      if (active) setState("checking");
    });
    if (verificationRequest?.key !== key) {
      verificationRequest = {
        key,
        promise: api.post("/auth/verify", { challengeId, token }),
      };
    }
    verificationRequest.promise
      .then(() => {
        if (active) setState("success");
      })
      .catch((err) => {
        if (!active) return;
        if (
          err instanceof ApiError &&
          err.code === "VERIFICATION_TOKEN_EXPIRED"
        )
          setState("expired");
        else if (
          err instanceof ApiError &&
          (err.status === 0 || err.status >= 500 || err.status === 429)
        )
          setState("temporary");
        else setState("failed");
      });
    return () => {
      active = false;
    };
  }, [challengeId, token, retryToken]);

  const body: Record<
    State,
    { variant: "default" | "destructive"; icon: typeof InfoIcon; text: string }
  > = {
    temporary: {
      variant: "destructive",
      icon: CircleAlertIcon,
      text: t("verify.temporary"),
    },
    checking: {
      variant: "default",
      icon: InfoIcon,
      text: t("verify.checking"),
    },
    success: {
      variant: "default",
      icon: CircleCheckIcon,
      text: t("verify.success"),
    },
    expired: {
      variant: "destructive",
      icon: CircleAlertIcon,
      text: t("verify.expired"),
    },
    failed: {
      variant: "destructive",
      icon: CircleAlertIcon,
      text: t("verify.failed"),
    },
    missing: {
      variant: "destructive",
      icon: CircleAlertIcon,
      text: t("verify.missingParams"),
    },
  };
  const current = body[state];
  const Icon = current.icon;

  return (
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 mx-auto max-w-sm space-y-6 duration-300 motion-reduce:animate-none">
      <h1 className="text-2xl font-bold text-foreground">
        {t("verify.title")}
      </h1>

      <Alert
        variant={current.variant}
        className={
          state === "success"
            ? "border-consent-active/40 text-consent-active"
            : undefined
        }
      >
        <Icon />
        <AlertDescription
          className={state === "success" ? "text-consent-active" : undefined}
        >
          {current.text}
        </AlertDescription>
      </Alert>

      {state === "success" && (
        <Button asChild className="h-11 w-full">
          <Link href="/login">{t("verify.continue")}</Link>
        </Button>
      )}
      {state === "temporary" && (
        <Button
          variant="outline"
          className="h-11 w-full"
          onClick={() => {
            verificationRequest = null;
            setRetryToken((n) => n + 1);
          }}
        >
          {t("verify.retry")}
        </Button>
      )}
      {(state === "expired" || state === "missing" || state === "failed") && (
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
