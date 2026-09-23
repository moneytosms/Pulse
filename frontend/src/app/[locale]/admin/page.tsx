"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { TriangleAlertIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import type { Me } from "@/lib/auth";

// Administrator-only entry point (issue #55). An Administrator reads no
// clinical data on any endpoint, ever (ADR-0007) — this dashboard and
// everything under `/admin` only ever surfaces identity fields and counts.
//
// Route protection: the backend already refuses every `/api/v1/admin/*`
// call to a non-Administrator with FORBIDDEN (`Permission.ADMIN_DUPLICATE_REVIEW`,
// enforced server-side and the only real guard). This client-side check exists
// only so a non-admin sees a clear message instead of a broken screen — there
// is no existing client-side role-gating convention elsewhere in the app to
// follow (every other protected screen relies solely on the backend's 401/404),
// so this is a new, minimal pattern: fetch `/auth/me`, compare `role`.
type GateState =
  | { status: "loading" }
  | { status: "denied" }
  | { status: "error"; message: string }
  | { status: "ready" };

export default function AdminDashboardPage() {
  const t = useTranslations("admin");
  const router = useRouter();
  const [gate, setGate] = useState<GateState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    api
      .get<Me>("/auth/me")
      .then((me) => {
        if (!active) return;
        setGate(me.role === "ADMINISTRATOR" ? { status: "ready" } : { status: "denied" });
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
        <AlertDescription>{gate.message}</AlertDescription>
      </Alert>
    );
  }

  return (
    <section className="space-y-8 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-1 motion-safe:duration-300">
      <div className="space-y-1">
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-pretty text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <Card>
        <CardHeader>
          {/* CardTitle renders a div (shadcn); this heading is asserted by
              e2e/phase4-admin-analytics.spec.ts via getByRole("heading"), so
              it needs real heading semantics — not something a className
              change on CardTitle can fix without touching ui/card.tsx. */}
          <CardTitle role="heading" aria-level={2}>
            {t("duplicateReview.title")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("duplicateReview.description")}</p>
          <Button asChild>
            <Link href="/admin/duplicates">{t("duplicateReview.cta")}</Link>
          </Button>
        </CardContent>
      </Card>
    </section>
  );
}
