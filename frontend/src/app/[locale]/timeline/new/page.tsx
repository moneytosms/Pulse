"use client";

import { useId, useState } from "react";
import type { FormEvent } from "react";
import { useTranslations } from "next-intl";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { useApiErrorMessage, useFieldErrors } from "@/lib/errors";
import {
  ENTRY_TYPES,
  uploadDocument,
  type EntryCreate,
  type EntryType,
} from "@/lib/records";

const CODED_TYPES = new Set<EntryType>(["DIAGNOSIS", "PROCEDURE", "LAB_REPORT"]);

// Focus order for jumping to the first invalid field after a 422 — mirrors
// the form's visual top-to-bottom order.
const FIELD_ORDER = [
  "patientId",
  "entryType",
  "occurredAt",
  "codeSystem",
  "code",
  "displayName",
  "valueNumeric",
  "valueText",
  "unit",
  "referenceLow",
  "referenceHigh",
  "medicationName",
  "dosage",
  "frequency",
  "route",
  "text",
];

// Provider Staff files an Entry for any Patient (clinical-safety.md:
// `patient.user_id` is nullable and load-bearing — a Patient need not have
// registered). There is no patient search screen yet, so the id is a plain
// field rather than an unbuilt picker (ponytail: no speculative UI).
export default function NewEntryPage() {
  const t = useTranslations("entry");
  const tTimeline = useTranslations("timeline");
  const errorMessage = useApiErrorMessage();
  const fieldErrors = useFieldErrors();
  const formId = useId();

  const [patientId, setPatientId] = useState("");
  const [entryType, setEntryType] = useState<EntryType | "">("");
  const [occurredAt, setOccurredAt] = useState("");
  const [isCritical, setIsCritical] = useState(false);
  const [codeSystem, setCodeSystem] = useState("");
  const [code, setCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [valueNumeric, setValueNumeric] = useState("");
  const [valueText, setValueText] = useState("");
  const [unit, setUnit] = useState("");
  const [referenceLow, setReferenceLow] = useState("");
  const [referenceHigh, setReferenceHigh] = useState("");
  const [medicationName, setMedicationName] = useState("");
  const [dosage, setDosage] = useState("");
  const [frequency, setFrequency] = useState("");
  const [route, setRoute] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [uploadFraction, setUploadFraction] = useState<number | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);

  const f = t.raw("new.fields") as Record<string, string>;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setErrors({});

    if (!patientId || !entryType || !occurredAt) {
      setFormError(t("new.validation.requiredFields"));
      return;
    }

    const parsedOccurredAt = new Date(occurredAt);
    if (Number.isNaN(parsedOccurredAt.getTime())) {
      setFormError(t("new.validation.requiredFields"));
      return;
    }

    const payload: EntryCreate = {
      entryType,
      occurredAt: parsedOccurredAt.toISOString(),
      isCritical,
      codeSystem: codeSystem || null,
      code: code || null,
      displayName: displayName || null,
      valueNumeric: valueNumeric ? Number(valueNumeric) : null,
      valueText: valueText || null,
      unit: unit || null,
      referenceLow: referenceLow ? Number(referenceLow) : null,
      referenceHigh: referenceHigh ? Number(referenceHigh) : null,
      medicationName: medicationName || null,
      dosage: dosage || null,
      frequency: frequency || null,
      route: route || null,
      text: text || null,
    };

    setSubmitting(true);
    try {
      const entry = await api.post<{ id: string }>(`/patients/${patientId}/entries`, payload);
      setCreatedId(entry.id);

      if (file) {
        setUploadFraction(0);
        try {
          await uploadDocument(patientId, entry.id, file, setUploadFraction);
        } catch (err) {
          setFormError(t("new.upload.failed", { reason: errorMessage(err) }));
        } finally {
          setUploadFraction(null);
        }
      }
    } catch (err) {
      const fields = fieldErrors(err);
      if (Object.keys(fields).length > 0) {
        setErrors(fields);
        const firstInvalid = FIELD_ORDER.find((name) => fields[name]);
        if (firstInvalid) {
          document.getElementById(`${formId}-${firstInvalid}`)?.focus();
        }
      }
      setFormError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (createdId) {
    return (
      <section className="mx-auto max-w-lg animate-in fade-in-0 slide-in-from-bottom-1 space-y-4 duration-300 motion-reduce:animate-none">
        <Alert className="border-consent-active/40 text-consent-active">
          <AlertTitle>{t("new.success.title")}</AlertTitle>
          <AlertDescription>{formError ?? t("new.success.body")}</AlertDescription>
        </Alert>
        <Button asChild>
          <Link href={`/timeline/${createdId}`}>{t("new.success.viewEntry")}</Link>
        </Button>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-lg animate-in fade-in-0 slide-in-from-bottom-1 space-y-8 duration-300 motion-reduce:animate-none">
      <div className="flex flex-col gap-1">
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
          {t("new.title")}
        </h1>
        <p className="text-pretty text-muted-foreground">{t("new.subtitle")}</p>
      </div>

      {formError && (
        <Alert variant="destructive">
          <AlertTitle>{t("new.title")}</AlertTitle>
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      )}

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <TextField
          formId={formId}
          name="patientId"
          label={f.patientId}
          value={patientId}
          onChange={setPatientId}
          error={errors.patientId}
        />

        <EntryTypeField
          formId={formId}
          label={f.entryType}
          value={entryType}
          onChange={setEntryType}
          error={errors.entryType}
          options={ENTRY_TYPES.map((type) => ({
            value: type,
            label: tTimeline(`entryTypes.${type}`),
          }))}
        />

        <TextField
          formId={formId}
          name="occurredAt"
          label={f.occurredAt}
          value={occurredAt}
          onChange={setOccurredAt}
          error={errors.occurredAt}
          type="datetime-local"
        />

        <div className="flex items-center gap-2">
          <Checkbox
            id={`${formId}-critical`}
            checked={isCritical}
            onCheckedChange={(checked) => setIsCritical(checked === true)}
          />
          <Label htmlFor={`${formId}-critical`}>{f.isCritical}</Label>
        </div>

        {entryType && CODED_TYPES.has(entryType) && (
          <>
            <TextField
              formId={formId}
              name="codeSystem"
              label={f.codeSystem}
              value={codeSystem}
              onChange={setCodeSystem}
              error={errors.codeSystem}
            />
            <TextField
              formId={formId}
              name="code"
              label={f.code}
              value={code}
              onChange={setCode}
              error={errors.code}
            />
            <TextField
              formId={formId}
              name="displayName"
              label={f.displayName}
              value={displayName}
              onChange={setDisplayName}
              error={errors.displayName}
            />
          </>
        )}

        {entryType === "LAB_REPORT" && (
          <>
            <TextField
              formId={formId}
              name="valueNumeric"
              label={f.valueNumeric}
              value={valueNumeric}
              onChange={setValueNumeric}
              error={errors.valueNumeric}
              type="number"
              inputMode="decimal"
            />
            <TextField
              formId={formId}
              name="valueText"
              label={f.valueText}
              value={valueText}
              onChange={setValueText}
              error={errors.valueText}
            />
            <TextField
              formId={formId}
              name="unit"
              label={f.unit}
              value={unit}
              onChange={setUnit}
              error={errors.unit}
            />
            <TextField
              formId={formId}
              name="referenceLow"
              label={f.referenceLow}
              value={referenceLow}
              onChange={setReferenceLow}
              error={errors.referenceLow}
              type="number"
              inputMode="decimal"
            />
            <TextField
              formId={formId}
              name="referenceHigh"
              label={f.referenceHigh}
              value={referenceHigh}
              onChange={setReferenceHigh}
              error={errors.referenceHigh}
              type="number"
              inputMode="decimal"
            />
          </>
        )}

        {entryType === "PRESCRIPTION" && (
          <>
            <TextField
              formId={formId}
              name="medicationName"
              label={f.medicationName}
              value={medicationName}
              onChange={setMedicationName}
              error={errors.medicationName}
            />
            <TextField
              formId={formId}
              name="dosage"
              label={f.dosage}
              value={dosage}
              onChange={setDosage}
              error={errors.dosage}
            />
            <TextField
              formId={formId}
              name="frequency"
              label={f.frequency}
              value={frequency}
              onChange={setFrequency}
              error={errors.frequency}
            />
            <TextField
              formId={formId}
              name="route"
              label={f.route}
              value={route}
              onChange={setRoute}
              error={errors.route}
            />
          </>
        )}

        {entryType === "CLINICAL_NOTE" && (
          <TextAreaField
            formId={formId}
            name="text"
            label={f.text}
            value={text}
            onChange={setText}
            error={errors.text}
          />
        )}

        <div className="space-y-1.5">
          <Label htmlFor={`${formId}-file`}>{f.file}</Label>
          <p className="text-xs text-muted-foreground">{t("new.fileHint")}</p>
          <input
            id={`${formId}-file`}
            type="file"
            accept="application/pdf,image/png,image/jpeg"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-foreground"
          />
        </div>

        {uploadFraction != null && (
          <div className="space-y-1">
            <p className="text-xs tabular-nums text-muted-foreground">
              {t("new.upload.inProgress", { percent: Math.round(uploadFraction * 100) })}
            </p>
            <Progress value={Math.round(uploadFraction * 100)} />
          </div>
        )}

        <Button type="submit" disabled={submitting} aria-busy={submitting} className="w-full">
          {submitting && <Spinner />}
          {submitting ? t("new.submitting") : t("new.submit")}
        </Button>
      </form>
    </section>
  );
}

function TextField({
  formId,
  name,
  label,
  value,
  onChange,
  error,
  type = "text",
  inputMode,
}: {
  formId: string;
  name: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  type?: string;
  inputMode?: "decimal";
}) {
  const inputId = `${formId}-${name}`;
  const errorId = `${inputId}-error`;
  return (
    <Field data-invalid={!!error || undefined}>
      <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
      <Input
        id={inputId}
        type={type}
        inputMode={inputMode}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={!!error}
        aria-describedby={error ? errorId : undefined}
      />
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </Field>
  );
}

function TextAreaField({
  formId,
  name,
  label,
  value,
  onChange,
  error,
}: {
  formId: string;
  name: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
}) {
  const inputId = `${formId}-${name}`;
  const errorId = `${inputId}-error`;
  return (
    <Field data-invalid={!!error || undefined}>
      <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
      <textarea
        id={inputId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={!!error}
        aria-describedby={error ? errorId : undefined}
        rows={5}
        className="block w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20"
      />
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </Field>
  );
}

function EntryTypeField({
  formId,
  label,
  value,
  onChange,
  error,
  options,
}: {
  formId: string;
  label: string;
  value: EntryType | "";
  onChange: (value: EntryType) => void;
  error?: string;
  options: Array<{ value: EntryType; label: string }>;
}) {
  const inputId = `${formId}-entryType`;
  const errorId = `${inputId}-error`;
  return (
    <Field data-invalid={!!error || undefined}>
      <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
      <Select value={value ?? ""} onValueChange={(v) => onChange(v as EntryType)}>
        <SelectTrigger
          id={inputId}
          aria-label={label}
          aria-invalid={!!error}
          aria-describedby={error ? errorId : undefined}
          className="w-full"
        >
          <SelectValue placeholder={label} />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </Field>
  );
}
