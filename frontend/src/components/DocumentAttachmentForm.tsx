"use client";

import { useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";
import { DocumentDropzone } from "@/components/DocumentDropzone";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { uploadDocument, type RecordDocument } from "@/lib/records";
import { useApiErrorMessage } from "@/lib/errors";

export function DocumentAttachmentForm({
  patientId,
  entryId,
  onAttached,
}: {
  patientId: string;
  entryId: string;
  onAttached: (doc: RecordDocument) => void;
}) {
  const t = useTranslations("entry");
  const errorMessage = useApiErrorMessage();
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attached, setAttached] = useState(false);
  const uploading = progress !== null;

  async function attach(event: FormEvent) {
    event.preventDefault();
    if (!file || uploading) return;
    setError(null);
    setAttached(false);
    setProgress(0);
    try {
      const doc = await uploadDocument(patientId, entryId, file, setProgress);
      onAttached(doc);
      setFile(null);
      setAttached(true);
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setProgress(null);
    }
  }
  return (
    <form
      onSubmit={attach}
      data-unsaved-changes={!!file}
      className="space-y-3 rounded-xl border bg-card p-4"
    >
      <DocumentDropzone
        label={t("new.fields.file")}
        hint={t("new.fileHint")}
        file={file}
        onFileChange={(value) => {
          setFile(value);
          setAttached(false);
        }}
        disabled={uploading}
        uploadFraction={progress}
      />
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {attached && <p role="status">{t("new.upload.attached")}</p>}
      <Button type="submit" disabled={!file || uploading} aria-busy={uploading}>
        {t(error ? "new.upload.retry" : "new.upload.attach")}
      </Button>
    </form>
  );
}
