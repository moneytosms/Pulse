"use client";

import { useId, useState } from "react";
import type { FormEvent } from "react";
import { useTranslations } from "next-intl";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Link } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import {
  CONSENT_PURPOSES,
  type ClinicianLookup,
  type Consent,
  type ConsentCreate,
  type ConsentPurpose,
} from "@/lib/consent";
import { useApiErrorMessage, useFieldErrors } from "@/lib/errors";
import { ENTRY_TYPES, type EntryType } from "@/lib/records";

// Scope is an entry-type + date-window picker only — never a per-entry
// checkbox list (.claude/rules/frontend.md, docs/domain-model.md). Leaving
// every entry type unchecked grants all of them (`entryTypes: null` on the
// wire), matching the backend's "no filter" meaning. The grantee is entered
// by email and resolved to a user id via `/clinicians/lookup` on submit.
export default function GrantConsentPage() {
  const t = useTranslations("consent");
  const tTimeline = useTranslations("timeline");
  const errorMessage = useApiErrorMessage();
  const fieldErrors = useFieldErrors();
  const formId = useId();
  const f = t.raw("new.fields") as Record<string, string>;

  const [granteeEmail, setGranteeEmail] = useState("");
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

    if (!granteeEmail.trim() || !purpose || !expiresAt) {
      setFormError(t("new.validation.requiredFields"));
      return;
    }

    const parsedExpiresAt = new Date(expiresAt);
    if (Number.isNaN(parsedExpiresAt.getTime())) {
      setFormError(t("new.validation.requiredFields"));
      return;
    }

    setSubmitting(true);
    let granteeUserId: string;
    try {
      const params = new URLSearchParams({ email: granteeEmail.trim() });
      granteeUserId = (await api.get<ClinicianLookup>(`/clinicians/lookup?${params}`)).userId;
    } catch (err) {
      setFormError(
        err instanceof ApiError && err.status === 404
          ? t("new.validation.clinicianNotFound")
          : errorMessage(err),
      );
      setSubmitting(false);
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
        <Alert className="border-consent-active/40 text-consent-active">
          <AlertTitle>{t("new.success.title")}</AlertTitle>
          <AlertDescription>{t("new.success.body")}</AlertDescription>
        </Alert>
        <Button asChild variant="link" className="px-0">
          <Link href="/consent">{t("new.success.viewConsents")}</Link>
        </Button>
      </section>
    );
  }

  const granteeEmailId = `${formId}-grantee-email`;
  const purposeTriggerId = `${formId}-purpose`;
  const purposeTextId = `${formId}-purpose-text`;
  const fromDateId = `${formId}-from-date`;
  const toDateId = `${formId}-to-date`;
  const expiresAtId = `${formId}-expires-at`;

  return (
    <section className="animate-in fade-in-0 slide-in-from-bottom-1 motion-reduce:animate-none mx-auto max-w-lg space-y-8 duration-300">
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <Link href="/consent">{t("list.title")}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{t("new.title")}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div className="space-y-1">
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
          {t("new.title")}
        </h1>
        <p className="text-pretty text-sm text-muted-foreground">{t("new.subtitle")}</p>
      </div>

      {formError && (
        <Alert variant="destructive">
          <AlertTitle>{t("new.title")}</AlertTitle>
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <Field data-invalid={!!errors.granteeUserId}>
          <FieldLabel htmlFor={granteeEmailId}>{f.granteeEmail}</FieldLabel>
          <Input
            id={granteeEmailId}
            type="email"
            autoComplete="off"
            aria-invalid={!!errors.granteeUserId}
            aria-describedby={errors.granteeUserId ? `${granteeEmailId}-error` : undefined}
            value={granteeEmail}
            onChange={(e) => setGranteeEmail(e.target.value)}
          />
          {errors.granteeUserId && (
            <FieldError id={`${granteeEmailId}-error`}>{errors.granteeUserId}</FieldError>
          )}
        </Field>

        <div className="space-y-1.5">
          <Label>{f.entryTypes}</Label>
          <p className="text-xs text-muted-foreground">{f.entryTypesHint}</p>
          <ul className="space-y-2">
            {ENTRY_TYPES.map((type) => {
              const checkboxId = `${formId}-type-${type}`;
              return (
                <li key={type} className="flex items-center gap-2">
                  <Checkbox
                    id={checkboxId}
                    checked={selectedTypes.has(type)}
                    onCheckedChange={(checked) => toggleType(type, checked === true)}
                  />
                  <Label htmlFor={checkboxId} className="font-normal text-foreground">
                    {tTimeline(`entryTypes.${type}`)}
                  </Label>
                </li>
              );
            })}
          </ul>
        </div>

        <Field data-invalid={!!errors.fromDate}>
          <FieldLabel htmlFor={fromDateId}>{f.fromDate}</FieldLabel>
          <Input
            id={fromDateId}
            type="date"
            aria-invalid={!!errors.fromDate}
            aria-describedby={errors.fromDate ? `${fromDateId}-error` : undefined}
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
          />
          {errors.fromDate && <FieldError id={`${fromDateId}-error`}>{errors.fromDate}</FieldError>}
        </Field>

        <Field data-invalid={!!errors.toDate}>
          <FieldLabel htmlFor={toDateId}>{f.toDate}</FieldLabel>
          <Input
            id={toDateId}
            type="date"
            aria-invalid={!!errors.toDate}
            aria-describedby={errors.toDate ? `${toDateId}-error` : undefined}
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
          />
          {errors.toDate && <FieldError id={`${toDateId}-error`}>{errors.toDate}</FieldError>}
        </Field>

        <Field data-invalid={!!errors.purpose}>
          <FieldLabel htmlFor={purposeTriggerId}>{f.purpose}</FieldLabel>
          <Select value={purpose ?? ""} onValueChange={(value) => setPurpose(value as ConsentPurpose)}>
            <SelectTrigger
              id={purposeTriggerId}
              aria-label={f.purpose}
              aria-invalid={!!errors.purpose}
              aria-describedby={errors.purpose ? `${purposeTriggerId}-error` : undefined}
              className="w-full"
            >
              <SelectValue placeholder={f.purpose} />
            </SelectTrigger>
            <SelectContent>
              {CONSENT_PURPOSES.map((p) => (
                <SelectItem key={p} value={p}>
                  {t(`list.purpose.${p}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {errors.purpose && <FieldError id={`${purposeTriggerId}-error`}>{errors.purpose}</FieldError>}
        </Field>

        {purpose === "OTHER" && (
          <Field data-invalid={!!errors.purposeText}>
            <FieldLabel htmlFor={purposeTextId}>{f.purposeText}</FieldLabel>
            <Input
              id={purposeTextId}
              aria-invalid={!!errors.purposeText}
              aria-describedby={errors.purposeText ? `${purposeTextId}-error` : undefined}
              value={purposeText}
              onChange={(e) => setPurposeText(e.target.value)}
            />
            {errors.purposeText && (
              <FieldError id={`${purposeTextId}-error`}>{errors.purposeText}</FieldError>
            )}
          </Field>
        )}

        <Field data-invalid={!!errors.expiresAt}>
          <FieldLabel htmlFor={expiresAtId}>{f.expiresAt}</FieldLabel>
          <Input
            id={expiresAtId}
            type="datetime-local"
            aria-invalid={!!errors.expiresAt}
            aria-describedby={errors.expiresAt ? `${expiresAtId}-error` : undefined}
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
          />
          {errors.expiresAt && <FieldError id={`${expiresAtId}-error`}>{errors.expiresAt}</FieldError>}
        </Field>

        <Button
          type="submit"
          disabled={submitting}
          aria-busy={submitting}
          className="min-h-11 w-full sm:min-h-8"
        >
          {submitting && <Spinner />}
          {submitting ? t("new.submitting") : t("new.submit")}
        </Button>
      </form>

      <Button asChild variant="link" className="min-h-11 px-0 sm:min-h-8">
        <Link href="/consent">{t("new.back")}</Link>
      </Button>
    </section>
  );
}
