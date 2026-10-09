"use client";

import { use, useEffect, useId, useState } from "react";
import type { FormEvent } from "react";
import { useTranslations } from "next-intl";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DocumentDropzone } from "@/components/DocumentDropzone";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import { useApiErrorMessage, useFieldErrors } from "@/lib/errors";
import {
  ENTRY_TYPES,
  uploadDocument,
  type EntryCreate,
  type EntryDetail,
  type EntryType,
} from "@/lib/records";

import type { Me } from "@/lib/auth";

const CODED_TYPES = new Set<EntryType>([
  "DIAGNOSIS",
  "PROCEDURE",
  "LAB_REPORT",
  "PRESCRIPTION",
]);

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
// field rather than an unbuilt picker (ponytail: no speculative UI). The
// patient record view links here with `?patientId=` so it arrives prefilled.
export default function NewEntryPage({
  searchParams,
}: {
  searchParams: Promise<{ patientId?: string; corrects?: string }>;
}) {
  const { patientId: initialPatientId, corrects } = use(searchParams);
  const t = useTranslations("entry");
  const tTimeline = useTranslations("timeline");
  const errorMessage = useApiErrorMessage();
  const fieldErrors = useFieldErrors();
  const formId = useId();
  const router = useRouter();
  const [gate, setGate] = useState<"loading" | "ready" | "denied" | "error">(
    "loading",
  );

  const [patientId, setPatientId] = useState(initialPatientId ?? "");
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
  const [uploadStatus, setUploadStatus] = useState<
    "idle" | "uploading" | "failed" | "attached"
  >("idle");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    let active = true;
    async function initialise() {
      try {
        const me = await api.get<Me>("/auth/me");
        if (!active) return;
        if (me.role !== "PROVIDER_STAFF" || !me.emailVerified) {
          setGate("denied");
          return;
        }
        if (corrects) {
          const entry = await api.get<EntryDetail>(
            `/entries/${encodeURIComponent(corrects)}`,
          );
          if (!active) return;
          if (entry.supersededById) {
            setFormError(t("correction.alreadyCorrected"));
            setGate("error");
            return;
          }
          setPatientId(entry.patientId);
          setEntryType(entry.entryType);
          const local = new Date(entry.occurredAt);
          setOccurredAt(
            new Date(local.getTime() - local.getTimezoneOffset() * 60000)
              .toISOString()
              .slice(0, 16),
          );
          setIsCritical(entry.isCritical);
          setCodeSystem(entry.codeSystem ?? "");
          setCode(entry.code ?? "");
          setDisplayName(entry.displayName ?? "");
          setValueNumeric(entry.valueNumeric?.toString() ?? "");
          setValueText(entry.valueText ?? "");
          setUnit(entry.unit ?? "");
          setReferenceLow(entry.referenceLow?.toString() ?? "");
          setReferenceHigh(entry.referenceHigh?.toString() ?? "");
          setMedicationName(entry.medicationName ?? "");
          setDosage(entry.dosage ?? "");
          setFrequency(entry.frequency ?? "");
          setRoute(entry.route ?? "");
          setText(entry.text ?? "");
        }
        setGate("ready");
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
          return;
        }
        setFormError(errorMessage(error));
        setGate("error");
      }
    }
    void initialise();
    return () => {
      active = false;
    };
    // Translation and router functions are stable for this page lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [corrects]);

  const f = t.raw("new.fields") as Record<string, string>;

  async function uploadSavedDocument(entryId: string, document: File) {
    setUploadFraction(0);
    setUploadStatus("uploading");
    setFormError(null);
    try {
      await uploadDocument(patientId, entryId, document, setUploadFraction);
      setUploadStatus("attached");
      setFile(null);
      setDirty(false);
    } catch (error) {
      setUploadStatus("failed");
      setFormError(t("new.upload.failed", { reason: errorMessage(error) }));
    } finally {
      setUploadFraction(null);
    }
  }

  async function retryUpload(event: FormEvent) {
    event.preventDefault();
    if (!createdId || !file || submitting) return;
    setSubmitting(true);
    try {
      await uploadSavedDocument(createdId, file);
    } finally {
      setSubmitting(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (gate !== "ready" || submitting || createdId) return;
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

    const coded = CODED_TYPES.has(entryType);
    const laboratory = entryType === "LAB_REPORT";
    const prescription = entryType === "PRESCRIPTION";
    // Keep drafts when switching types, but never send hidden subtype fields.
    // In particular, an unfinished lab range must not invalidate a note.
    const payload: EntryCreate = {
      entryType,
      occurredAt: parsedOccurredAt.toISOString(),
      isCritical,
      codeSystem: coded ? codeSystem || null : null,
      code: coded ? code || null : null,
      displayName: coded ? displayName || null : null,
      valueNumeric: laboratory && valueNumeric ? Number(valueNumeric) : null,
      valueText: laboratory ? valueText || null : null,
      unit: laboratory ? unit || null : null,
      referenceLow: laboratory && referenceLow ? Number(referenceLow) : null,
      referenceHigh: laboratory && referenceHigh ? Number(referenceHigh) : null,
      medicationName: prescription ? medicationName || null : null,
      dosage: prescription ? dosage || null : null,
      frequency: prescription ? frequency || null : null,
      route: prescription ? route || null : null,
      text: entryType === "CLINICAL_NOTE" ? text || null : null,
    };

    setSubmitting(true);
    try {
      const entry = await api.post<{ id: string }>(
        `/patients/${encodeURIComponent(patientId)}/entries${corrects ? `/${encodeURIComponent(corrects)}/corrections` : ""}`,
        payload,
      );
      setCreatedId(entry.id);

      setDirty(false);
      if (file) await uploadSavedDocument(entry.id, file);
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

  if (gate !== "ready") {
    return (
      <section className="mx-auto max-w-lg space-y-4">
        <h1 className="text-2xl font-semibold">{t("new.title")}</h1>
        {gate === "loading" ? (
          <p role="status">{t("gate.loading")}</p>
        ) : (
          <Alert variant={gate === "error" ? "destructive" : "default"}>
            <AlertTitle>{t("gate.title")}</AlertTitle>
            <AlertDescription>{formError ?? t("gate.denied")}</AlertDescription>
          </Alert>
        )}
      </section>
    );
  }

  if (createdId) {
    return (
      <section className="mx-auto max-w-lg animate-in fade-in-0 slide-in-from-bottom-1 space-y-4 duration-300 motion-reduce:animate-none">
        <Alert variant={uploadStatus === "failed" ? "destructive" : "default"}>
          <AlertTitle>
            {t(corrects ? "correction.success" : "new.success.title")}
          </AlertTitle>
          <AlertDescription>
            {uploadStatus === "uploading"
              ? t("new.upload.keepOpen")
              : (formError ??
                (uploadStatus === "attached"
                  ? t("new.upload.attached")
                  : t(
                      corrects ? "correction.successBody" : "new.success.body",
                    )))}
          </AlertDescription>
        </Alert>
        {uploadStatus !== "idle" && uploadStatus !== "attached" && (
          <form
            onSubmit={retryUpload}
            data-unsaved-changes={!!file}
            className="space-y-4"
          >
            <DocumentDropzone
              label={f.file}
              hint={t("new.fileHint")}
              file={file}
              onFileChange={setFile}
              disabled={submitting}
              uploadFraction={uploadFraction}
            />
            {uploadStatus === "failed" && (
              <Button
                type="submit"
                disabled={submitting || !file}
                aria-busy={submitting}
              >
                {t("new.upload.retry")}
              </Button>
            )}
          </form>
        )}

        <Button asChild>
          <Link
            href={`/patients/${patientId}/records/${createdId}`}
            onClick={(event) => {
              if (submitting && !window.confirm(t("new.upload.leaveWarning")))
                event.preventDefault();
            }}
          >
            {t("new.success.viewEntry")}
          </Link>
        </Button>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-lg animate-in fade-in-0 slide-in-from-bottom-1 space-y-8 duration-300 motion-reduce:animate-none">
      <div className="flex flex-col gap-1">
        <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
          {t(corrects ? "correction.title" : "new.title")}
        </h1>
        <p className="text-pretty text-muted-foreground">
          {t(corrects ? "correction.subtitle" : "new.subtitle")}
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
        aria-busy={submitting}
      >
        <fieldset
          disabled={submitting}
          aria-label={t(corrects ? "correction.title" : "new.title")}
          className="min-w-0 space-y-4"
        >
          <TextField
            formId={formId}
            name="patientId"
            label={f.patientId}
            value={patientId}
            onChange={setPatientId}
            error={errors.patientId}
            readOnly={!!corrects}
          />

          <EntryTypeField
            formId={formId}
            label={f.entryType}
            value={entryType}
            onChange={(value) => {
              setEntryType(value);
              setDirty(true);
            }}
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
              onCheckedChange={(checked) => {
                setIsCritical(checked === true);
                setDirty(true);
              }}
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

          <DocumentDropzone
            label={f.file}
            hint={t("new.fileHint")}
            file={file}
            onFileChange={(value) => {
              setFile(value);
              setDirty(true);
            }}
            disabled={submitting}
            uploadFraction={uploadFraction}
          />

          <Button
            type="submit"
            disabled={submitting}
            aria-busy={submitting}
            className="w-full"
          >
            {submitting && <Spinner />}
            {submitting
              ? t("new.submitting")
              : t(corrects ? "correction.submit" : "new.submit")}
          </Button>
        </fieldset>
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
  readOnly = false,
}: {
  formId: string;
  name: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  type?: string;
  inputMode?: "decimal";
  readOnly?: boolean;
}) {
  const inputId = `${formId}-${name}`;
  const errorId = `${inputId}-error`;
  return (
    <Field data-invalid={!!error || undefined}>
      <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
      <Input
        id={inputId}
        type={type}
        readOnly={readOnly}
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
      <Select
        value={value ?? ""}
        onValueChange={(v) => onChange(v as EntryType)}
      >
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
