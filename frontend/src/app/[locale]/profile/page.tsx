"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Callout } from "@/components/ui/Callout";
import { Link, useRouter } from "@/i18n/navigation";
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

  if (state.status === "loading") {
    return <p className="text-sm text-muted">{t("loading")}</p>;
  }
  if (state.status === "notFound") {
    return (
      <Callout tone="info" iconLabel={t("title")}>
        {t("notFound")}
      </Callout>
    );
  }
  if (state.status === "error") {
    return (
      <Callout tone="error" iconLabel={t("title")}>
        {state.message}
      </Callout>
    );
  }

  const { profile } = state;
  const localeLabel =
    profile.localePreference === "en" || profile.localePreference === "hi"
      ? tLocale(profile.localePreference)
      : profile.localePreference;

  const show = (value: string | null): string => value?.trim() || EMPTY;

  const rows: Array<[string, string]> = [
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
    <section className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted">{t("subtitle")}</p>
      </div>

      <dl className="divide-y divide-border rounded-md border border-border bg-surface">
        {rows.map(([label, value]) => (
          <div
            key={label}
            className="grid grid-cols-1 gap-1 px-4 py-3 sm:grid-cols-3 sm:gap-4"
          >
            <dt className="text-sm font-medium text-muted">{label}</dt>
            <dd className="text-sm text-foreground tabular-nums sm:col-span-2">
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-wrap gap-4">
        <Link href="/consent" className="text-sm font-medium text-accent-text underline">
          {t("links.consent")}
        </Link>
        <Link href="/audit" className="text-sm font-medium text-accent-text underline">
          {t("links.audit")}
        </Link>
      </div>
    </section>
  );
}
