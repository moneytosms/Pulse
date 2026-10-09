"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
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
import { formatDate, formatDateTime } from "@/lib/format";
import { ENTRY_TYPES, type EntryType } from "@/lib/records";

// Scope is explicit. The reviewed payload is frozen until the user edits it.
// Granting retains password step-up; revoking remains frictionless.
export default function GrantConsentPage() {
  const locale = useLocale();
  const t = useTranslations("consent");
  const tTimeline = useTranslations("timeline");
  const errorMessage = useApiErrorMessage();
  const fieldErrors = useFieldErrors();
  const formId = useId();
  const f = t.raw("new.fields") as Record<string, string>;

  const [granteeEmail, setGranteeEmail] = useState("");
  const [scope, setScope] = useState<"" | "all" | "selected">("");
  const [review, setReview] = useState<{
    clinician: ClinicianLookup;
    payload: ConsentCreate;
  } | null>(null);
  const reviewHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (review) reviewHeading.current?.focus();
  }, [review]);
  const [selectedTypes, setSelectedTypes] = useState<Set<EntryType>>(new Set());
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [purpose, setPurpose] = useState<ConsentPurpose | "">("");
  const [purposeText, setPurposeText] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [password, setPassword] = useState("");

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [granted, setGranted] = useState<Consent | null>(null);

  function toggleType(type: EntryType, checked: boolean) {
    setDirty(true);
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

    if (submitting) return;
    if (!review) {
      if (!granteeEmail.trim() || !purpose || !expiresAt) {
        setFormError(t("new.validation.requiredFields"));
        return;
      }
      if (!scope || (scope === "selected" && selectedTypes.size === 0)) {
        setFormError(t("new.validation.scopeRequired"));
        return;
      }
      const expiry = new Date(expiresAt);
      if (Number.isNaN(expiry.getTime()) || expiry.getTime() <= Date.now()) {
        setFormError(t("new.validation.expiryFuture"));
        return;
      }
      if (fromDate && toDate && fromDate > toDate) {
        setFormError(t("new.validation.dateOrder"));
        return;
      }
      if (purpose === "OTHER" && !purposeText.trim()) {
        setFormError(t("new.validation.purposeRequired"));
        return;
      }
      setSubmitting(true);
      try {
        const params = new URLSearchParams({ email: granteeEmail.trim() });
        const clinician = await api.get<ClinicianLookup>(
          `/clinicians/lookup?${params}`,
        );
        setReview({
          clinician,
          payload: {
            granteeUserId: clinician.userId,
            entryTypes: scope === "all" ? null : Array.from(selectedTypes),
            fromDate: fromDate || null,
            toDate: toDate || null,
            purpose,
            purposeText: purpose === "OTHER" ? purposeText.trim() : null,
            expiresAt: expiry.toISOString(),
          },
        });
      } catch (err) {
        setFormError(
          err instanceof ApiError && err.status === 404
            ? t("new.validation.clinicianNotFound")
            : errorMessage(err),
        );
      } finally {
        setSubmitting(false);
      }
      return;
    }
    if (!password) {
      setFormError(t("new.validation.passwordRequired"));
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/auth/step-up", { password });
    } catch (err) {
      setFormError(
        err instanceof ApiError && err.code === "INVALID_CREDENTIALS"
          ? t("new.validation.wrongPassword")
          : errorMessage(err),
      );
      setSubmitting(false);
      return;
    }
    const payload = review.payload;

    try {
      const consent = await api.post<Consent>("/consents", payload);
      setGranted(consent);
      setPassword("");
      setDirty(false);
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
          <AlertDescription>
            {t("new.success.details", {
              email: review?.clinician.email ?? granteeEmail,
              types:
                granted.entryTypes
                  ?.map((type) => tTimeline(`entryTypes.${type}`))
                  .join(", ") ?? t("list.scope.allTypes"),
              expiry: formatDateTime(granted.expiresAt, `${locale}-IN`),
            })}
          </AlertDescription>
        </Alert>
        <Button
          asChild
          variant="link"
          className="h-auto max-w-full justify-start whitespace-normal px-0 py-2 text-left"
        >
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
  const passwordId = `${formId}-password`;

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
        <p className="text-pretty text-sm text-muted-foreground">
          {t("new.subtitle")}
        </p>
      </div>

      {formError && (
        <Alert variant="destructive">
          <AlertTitle>{t("new.title")}</AlertTitle>
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}

      <form
        onSubmit={onSubmit}
        noValidate
        data-unsaved-changes={dirty || submitting}
        onChange={() => setDirty(true)}
        className="space-y-6"
      >
        {!review && (
          <fieldset disabled={submitting} className="min-w-0 space-y-5">
            <Field data-invalid={!!errors.granteeUserId}>
              <FieldLabel htmlFor={granteeEmailId}>{f.granteeEmail}</FieldLabel>
              <Input
                id={granteeEmailId}
                type="email"
                autoComplete="off"
                aria-invalid={!!errors.granteeUserId}
                aria-describedby={
                  errors.granteeUserId ? `${granteeEmailId}-error` : undefined
                }
                value={granteeEmail}
                onChange={(e) => setGranteeEmail(e.target.value)}
              />
              {errors.granteeUserId && (
                <FieldError id={`${granteeEmailId}-error`}>
                  {errors.granteeUserId}
                </FieldError>
              )}
            </Field>

            <fieldset className="min-w-0 space-y-3">
              <legend className="text-sm font-medium">{f.entryTypes}</legend>
              <p className="text-sm text-muted-foreground">
                {t("new.scope.hint")}
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {(["all", "selected"] as const).map((choice) => (
                  <label
                    key={choice}
                    className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border p-3 has-checked:border-primary has-checked:bg-primary/5"
                  >
                    <input
                      type="radio"
                      name={`${formId}-scope`}
                      value={choice}
                      checked={scope === choice}
                      onChange={() => {
                        setScope(choice);
                        setDirty(true);
                      }}
                      className="size-4 accent-primary"
                    />
                    {t(`new.scope.${choice}`)}
                  </label>
                ))}
              </div>
              {scope === "selected" && (
                <ul className="grid gap-1 sm:grid-cols-2">
                  {ENTRY_TYPES.map((type) => {
                    const checkboxId = `${formId}-type-${type}`;
                    return (
                      <li key={type}>
                        <Label
                          htmlFor={checkboxId}
                          className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-2 font-normal text-foreground hover:bg-muted"
                        >
                          <Checkbox
                            id={checkboxId}
                            checked={selectedTypes.has(type)}
                            onCheckedChange={(checked) =>
                              toggleType(type, checked === true)
                            }
                          />
                          {tTimeline(`entryTypes.${type}`)}
                        </Label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </fieldset>
            <p className="text-sm text-muted-foreground">
              {t("new.scope.historyHint")}
            </p>

            <Field data-invalid={!!errors.fromDate}>
              <FieldLabel htmlFor={fromDateId}>{f.fromDate}</FieldLabel>
              <Input
                id={fromDateId}
                type="date"
                aria-invalid={!!errors.fromDate}
                aria-describedby={
                  errors.fromDate ? `${fromDateId}-error` : undefined
                }
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
              />
              {errors.fromDate && (
                <FieldError id={`${fromDateId}-error`}>
                  {errors.fromDate}
                </FieldError>
              )}
            </Field>

            <Field data-invalid={!!errors.toDate}>
              <FieldLabel htmlFor={toDateId}>{f.toDate}</FieldLabel>
              <Input
                id={toDateId}
                type="date"
                aria-invalid={!!errors.toDate}
                aria-describedby={
                  errors.toDate ? `${toDateId}-error` : undefined
                }
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
              />
              {errors.toDate && (
                <FieldError id={`${toDateId}-error`}>
                  {errors.toDate}
                </FieldError>
              )}
            </Field>

            <Field data-invalid={!!errors.purpose}>
              <FieldLabel htmlFor={purposeTriggerId}>{f.purpose}</FieldLabel>
              <Select
                value={purpose ?? ""}
                onValueChange={(value) => {
                  setPurpose(value as ConsentPurpose);
                  setDirty(true);
                }}
              >
                <SelectTrigger
                  id={purposeTriggerId}
                  aria-label={f.purpose}
                  aria-invalid={!!errors.purpose}
                  aria-describedby={
                    errors.purpose ? `${purposeTriggerId}-error` : undefined
                  }
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
              {errors.purpose && (
                <FieldError id={`${purposeTriggerId}-error`}>
                  {errors.purpose}
                </FieldError>
              )}
            </Field>

            {purpose === "OTHER" && (
              <Field data-invalid={!!errors.purposeText}>
                <FieldLabel htmlFor={purposeTextId}>{f.purposeText}</FieldLabel>
                <Input
                  id={purposeTextId}
                  aria-invalid={!!errors.purposeText}
                  aria-describedby={
                    errors.purposeText ? `${purposeTextId}-error` : undefined
                  }
                  value={purposeText}
                  onChange={(e) => setPurposeText(e.target.value)}
                />
                {errors.purposeText && (
                  <FieldError id={`${purposeTextId}-error`}>
                    {errors.purposeText}
                  </FieldError>
                )}
              </Field>
            )}

            <Field data-invalid={!!errors.expiresAt}>
              <FieldLabel htmlFor={expiresAtId}>{f.expiresAt}</FieldLabel>
              <Input
                id={expiresAtId}
                type="datetime-local"
                aria-invalid={!!errors.expiresAt}
                aria-describedby={
                  errors.expiresAt ? `${expiresAtId}-error` : undefined
                }
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
              />
              {errors.expiresAt && (
                <FieldError id={`${expiresAtId}-error`}>
                  {errors.expiresAt}
                </FieldError>
              )}
            </Field>
          </fieldset>
        )}
        {review && (
          <section
            className="space-y-4 rounded-xl border bg-muted/30 p-4"
            aria-labelledby={`${formId}-review`}
          >
            <h2
              ref={reviewHeading}
              tabIndex={-1}
              id={`${formId}-review`}
              className="text-lg font-semibold"
            >
              {t("new.review.title")}
            </h2>
            <dl className="space-y-3 text-sm">
              {[
                [f.granteeEmail, review.clinician.email],
                [
                  f.entryTypes,
                  review.payload.entryTypes
                    ?.map((type) => tTimeline(`entryTypes.${type}`))
                    .join(", ") ?? t("list.scope.allTypes"),
                ],
                [
                  t("new.review.history"),
                  `${review.payload.fromDate ? formatDate(review.payload.fromDate) : t("new.review.beginning")} – ${review.payload.toDate ? formatDate(review.payload.toDate) : t("new.review.latest")}`,
                ],
                [
                  f.purpose,
                  t(`list.purpose.${review.payload.purpose}`) +
                    (review.payload.purposeText
                      ? `: ${review.payload.purposeText}`
                      : ""),
                ],
                [
                  f.expiresAt,
                  formatDateTime(review.payload.expiresAt, `${locale}-IN`),
                ],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="break-words font-medium">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="text-sm text-muted-foreground">
              {t("new.review.revokeHint")}
            </p>
            <Button
              type="button"
              variant="outline"
              disabled={submitting}
              onClick={() => {
                setReview(null);
                setPassword("");
                setFormError(null);
              }}
            >
              {t("new.review.edit")}
            </Button>
          </section>
        )}
        {review && (
          <Field>
            <FieldLabel htmlFor={passwordId}>{f.password}</FieldLabel>
            <Input
              id={passwordId}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
        )}

        <Button
          type="submit"
          disabled={submitting}
          aria-busy={submitting}
          className="min-h-11 w-full sm:min-h-8"
        >
          {submitting && <Spinner />}
          {submitting
            ? t(review ? "new.submitting" : "new.review.checking")
            : review
              ? t("new.submit")
              : t("new.review.continue")}
        </Button>
      </form>

      <Button
        asChild
        variant="link"
        className="h-auto min-h-11 max-w-full justify-start whitespace-normal px-0 py-2 text-left sm:min-h-8"
      >
        <Link href="/consent">{t("new.back")}</Link>
      </Button>
    </section>
  );
}
