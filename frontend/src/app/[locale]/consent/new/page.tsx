"use client";

import { useId, useState } from "react";
import type { FormEvent } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Checkbox } from "@/components/ui/Checkbox";
import { FormField } from "@/components/ui/FormField";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { CONSENT_PURPOSES, type Consent, type ConsentCreate, type ConsentPurpose } from "@/lib/consent";
import { useApiErrorMessage, useFieldErrors } from "@/lib/errors";
import { ENTRY_TYPES, type EntryType } from "@/lib/records";

// Scope is an entry-type + date-window picker only — never a per-entry
// checkbox list (.claude/rules/frontend.md, docs/domain-model.md). Leaving
// every entry type unchecked grants all of them (`entryTypes: null` on the
// wire), matching the backend's "no filter" meaning.
export default function GrantConsentPage() {
  const t = useTranslations("consent");
  const tTimeline = useTranslations("timeline");
  const errorMessage = useApiErrorMessage();
  const fieldErrors = useFieldErrors();
  const formId = useId();
  const f = t.raw("new.fields") as Record<string, string>;

  const [granteeUserId, setGranteeUserId] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<Set<EntryType>>(new Set());
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [purpose, setPurpose] = useState<ConsentPurpose | "">("");
  const [purposeText, setPurposeText] = useState("");
  const [expiresAt, setExpiresAt] = useState("");

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [granted, setGranted] = useState<Consent | null>(null);

  function toggleType(type: EntryType, checked: boolean) {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (checked) next.add(type);
      else next.delete(type);
      return next;
    });
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setErrors({});

    if (!granteeUserId || !purpose || !expiresAt) {
      setFormError(t("new.validation.requiredFields"));
      return;
    }

    const parsedExpiresAt = new Date(expiresAt);
    if (Number.isNaN(parsedExpiresAt.getTime())) {
      setFormError(t("new.validation.requiredFields"));
      return;
    }

    const payload: ConsentCreate = {
      granteeUserId,
      entryTypes: selectedTypes.size > 0 ? Array.from(selectedTypes) : null,
      fromDate: fromDate || null,
      toDate: toDate || null,
      purpose,
      purposeText: purpose === "OTHER" ? purposeText || null : null,
      expiresAt: parsedExpiresAt.toISOString(),
    };

    setSubmitting(true);
    try {
      const consent = await api.post<Consent>("/consents", payload);
      setGranted(consent);
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) setErrors(fields);
      setFormError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (granted) {
    return (
      <section className="mx-auto max-w-lg space-y-4">
        <Callout tone="success" iconLabel={t("new.success.title")}>
          {t("new.success.body")}
        </Callout>
        <Link href="/consent" className="text-sm font-medium text-accent-text underline">
          {t("new.success.viewConsents")}
        </Link>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-lg space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-foreground">{t("new.title")}</h1>
        <p className="text-sm text-muted">{t("new.subtitle")}</p>
      </div>

      {formError && (
        <Callout tone="error" iconLabel={t("new.title")}>
          {formError}
        </Callout>
      )}

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <FormField label={f.granteeUserId} error={errors.granteeUserId}>
          {(props) => (
            <Input
              {...props}
              value={granteeUserId}
              onChange={(e) => setGranteeUserId(e.target.value)}
            />
          )}
        </FormField>

        <div className="space-y-1.5">
          <Label>{f.entryTypes}</Label>
          <p className="text-xs text-muted">{f.entryTypesHint}</p>
          <ul className="space-y-2">
            {ENTRY_TYPES.map((type) => {
              const checkboxId = `${formId}-type-${type}`;
              return (
                <li key={type} className="flex items-center gap-2">
                  <Checkbox
                    id={checkboxId}
                    checked={selectedTypes.has(type)}
                    onCheckedChange={(checked) => toggleType(type, checked)}
                  />
                  <label htmlFor={checkboxId} className="text-sm text-foreground">
                    {tTimeline(`entryTypes.${type}`)}
                  </label>
                </li>
              );
            })}
          </ul>
        </div>

        <FormField label={f.fromDate} error={errors.fromDate}>
          {(props) => (
            <Input {...props} type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
          )}
        </FormField>

        <FormField label={f.toDate} error={errors.toDate}>
          {(props) => (
            <Input {...props} type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
          )}
        </FormField>

        <FormField label={f.purpose} error={errors.purpose}>
          {(props) => (
            <Select
              {...props}
              value={purpose || undefined}
              onValueChange={(value) => setPurpose(value as ConsentPurpose)}
              placeholder={f.purpose}
              options={CONSENT_PURPOSES.map((p) => ({
                value: p,
                label: t(`list.purpose.${p}`),
              }))}
            />
          )}
        </FormField>

        {purpose === "OTHER" && (
          <FormField label={f.purposeText} error={errors.purposeText}>
            {(props) => (
              <Input {...props} value={purposeText} onChange={(e) => setPurposeText(e.target.value)} />
            )}
          </FormField>
        )}

        <FormField label={f.expiresAt} error={errors.expiresAt}>
          {(props) => (
            <Input
              {...props}
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
            />
          )}
        </FormField>

        <Button type="submit" loading={submitting} className="w-full">
          {submitting ? t("new.submitting") : t("new.submit")}
        </Button>
      </form>

      <Link href="/consent" className="block text-sm font-medium text-accent-text underline">
        {t("new.back")}
      </Link>
    </section>
  );
}
