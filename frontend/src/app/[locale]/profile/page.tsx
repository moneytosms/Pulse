"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { InfoIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApiErrorMessage } from "@/lib/errors";

// Identity fields only — the patient profile carries no clinical data
// (issue #23, PatientProfile schema; .claude/rules/clinical-safety.md).
interface PatientProfile {
  id: string;
  fullName: string;
  // Nullable in the backend schema — an unclaimed or freshly registered
  // Patient has only a name until identity data is filed.
  dateOfBirth: string | null;
  sex: string | null;
  phone: string | null;
  addressLine: string | null;
  city: string | null;
  state: string | null;
  localePreference: string;
  claimed: boolean;
}

const EMPTY = "—"; // em dash for a missing identity field

type LoadState =
  | { status: "loading" }
  | { status: "ready"; profile: PatientProfile }
  | { status: "notFound" }
  | { status: "error"; message: string };

function ProfileSkeleton() {
  return (
    <Card aria-hidden="true">
      <CardContent className="divide-y divide-border p-0">
        {Array.from({ length: 9 }).map((_, i) => (
          <div key={i} className="grid grid-cols-1 gap-1 px-4 py-3 sm:grid-cols-3 sm:gap-4">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-40 sm:col-span-2" />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function ProfilePage() {
  const t = useTranslations("profile");
  const tLocale = useTranslations("locale");
  const errorMessage = useApiErrorMessage();
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    api
      .get<PatientProfile>("/patients/me")
      .then((profile) => {
        if (active) setState({ status: "ready", profile });
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && (err.status === 401 || err.code === "SESSION_EXPIRED")) {
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
  }, []);

  const header = (
    <div className="space-y-1">
      <h1 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
        {t("title")}
      </h1>
      <p className="text-sm text-pretty text-muted-foreground">{t("subtitle")}</p>
    </div>
  );

  if (state.status === "loading") {
    return (
      <section className="animate-in fade-in-0 slide-in-from-bottom-1 duration-300 motion-reduce:animate-none space-y-8">
        {header}
        <span className="sr-only">{t("loading")}</span>
        <ProfileSkeleton />
      </section>
    );
  }
  if (state.status === "notFound") {
    return (
      <section className="space-y-8">
        {header}
        <Alert>
          <InfoIcon />
          <AlertTitle>{t("title")}</AlertTitle>
          <AlertDescription>{t("notFound")}</AlertDescription>
        </Alert>
      </section>
    );
  }
  if (state.status === "error") {
    return (
      <section className="space-y-8">
        {header}
        <Alert variant="destructive">
          <InfoIcon />
          <AlertTitle>{t("title")}</AlertTitle>
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      </section>
    );
  }

  const { profile } = state;
  const localeLabel = (routing.locales as readonly string[]).includes(profile.localePreference)
    ? tLocale(profile.localePreference as (typeof routing.locales)[number])
    : profile.localePreference;

  const show = (value: string | null): string => value?.trim() || EMPTY;

  const rows: Array<[string, string]> = [
    [t("fields.patientId"), profile.id],
    [t("fields.fullName"), show(profile.fullName)],
    [t("fields.dateOfBirth"), formatDate(profile.dateOfBirth) || EMPTY],
    [t("fields.sex"), show(profile.sex)],
    [t("fields.phone"), show(profile.phone)],
    [t("fields.addressLine"), show(profile.addressLine)],
    [t("fields.city"), show(profile.city)],
    [t("fields.state"), show(profile.state)],
    [t("fields.localePreference"), localeLabel],
    [t("claimed.label"), profile.claimed ? t("claimed.true") : t("claimed.false")],
  ];

  return (
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 duration-300 motion-reduce:animate-none space-y-8">
      {header}

      <Card>
        <CardContent className="p-0">
          <dl className="divide-y divide-border">
            {rows.map(([label, value]) => (
              <div
                key={label}
                className="grid grid-cols-1 gap-1 px-4 py-3 sm:grid-cols-3 sm:gap-4"
              >
                <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
                <dd className="text-sm text-foreground tabular-nums sm:col-span-2">{value}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
      <p className="text-xs text-pretty text-muted-foreground">{t("patientIdHint")}</p>
    </section>
  );
}
