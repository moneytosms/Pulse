"use client";

import { useId, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { FileText, Upload, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

const ACCEPTED_MIME_TYPES = new Set([
  "application/pdf",
  "image/png",
  "image/jpeg",
]);
const ACCEPTED_FILE_NAMES = /\.(pdf|png|jpe?g)$/i;
const ACCEPTED_FILE_TYPES = "application/pdf,image/png,image/jpeg";

interface DocumentDropzoneProps {
  label: string;
  hint: string;
  file: File | null;
  onFileChange: (file: File | null) => void;
  disabled?: boolean;
  uploadFraction?: number | null;
}

function isAcceptedFile(file: File): boolean {
  return ACCEPTED_MIME_TYPES.has(file.type) || ACCEPTED_FILE_NAMES.test(file.name);
}

function formatFileSize(bytes: number, locale: string): string {
  const formatter = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  if (bytes < 1024) return `${formatter.format(bytes)} B`;
  if (bytes < 1024 * 1024) return `${formatter.format(bytes / 1024)} KB`;
  return `${formatter.format(bytes / (1024 * 1024))} MB`;
}

export function DocumentDropzone({
  label,
  hint,
  file,
  onFileChange,
  disabled = false,
  uploadFraction = null,
}: DocumentDropzoneProps) {
  const t = useTranslations("entry");
  const locale = useLocale();
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const progress = uploadFraction == null ? null : Math.round(uploadFraction * 100);

  function chooseFiles(files: FileList | File[]) {
    const selected = Array.from(files);
    if (selected.length === 0) return;
    if (selected.length > 1) {
      setSelectionError(t("new.dropzone.oneAtATime"));
      return;
    }

    const nextFile = selected[0];
    if (!nextFile || !isAcceptedFile(nextFile)) {
      setSelectionError(t("new.dropzone.unsupported"));
      return;
    }

    setSelectionError(null);
    onFileChange(nextFile);
  }

  function onInputChange(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    if (input.files) chooseFiles(input.files);
    // Let users select the same file again after removing it.
    input.value = "";
  }

  function onDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (!disabled) setDragging(true);
  }

  function onDragLeave(event: DragEvent<HTMLDivElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setDragging(false);
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (!disabled) chooseFiles(event.dataTransfer.files);
  }

  function openFilePicker() {
    if (!disabled) inputRef.current?.click();
  }

  function removeFile() {
    setSelectionError(null);
    onFileChange(null);
  }

  return (
    <div className="space-y-2">
      <Label id={`${id}-label`} htmlFor={`${id}-input`} className="text-sm font-medium">
        {label}
      </Label>
      <p id={`${id}-hint`} className="text-xs text-muted-foreground">
        {hint}
      </p>
      <input
        ref={inputRef}
        id={`${id}-input`}
        type="file"
        accept={ACCEPTED_FILE_TYPES}
        onChange={onInputChange}
        disabled={disabled}
        tabIndex={-1}
        className="sr-only"
        aria-describedby={`${id}-hint`}
      />

      <div
        data-testid="document-dropzone"
        role="group"
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-hint`}
        aria-disabled={disabled}
        onDragEnter={onDragOver}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={cn(
          "rounded-xl border border-dashed p-4 transition-colors sm:p-5",
          "has-[:focus-visible]:border-ring has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/40",
          dragging && "border-primary bg-primary/5",
          !dragging && "border-border bg-muted/20",
          disabled && "opacity-60",
          "motion-reduce:transition-none",
        )}
      >
        {file ? (
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-3" aria-live="polite">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <FileText aria-hidden="true" className="size-5" />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-foreground">
                  {file.name}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {formatFileSize(file.size, locale)}
                </span>
              </span>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={openFilePicker}
                disabled={disabled}
              >
                {t("new.dropzone.replace")}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={removeFile}
                disabled={disabled}
                aria-label={t("new.dropzone.remove")}
              >
                <X aria-hidden="true" />
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-3 text-center">
            <span className="flex size-11 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Upload aria-hidden="true" className="size-5" />
            </span>
            <div className="space-y-1">
              <p className="text-sm font-medium text-foreground">
                {t("new.dropzone.prompt")}
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={openFilePicker}
              disabled={disabled}
            >
              {t("new.dropzone.browse")}
            </Button>
          </div>
        )}
      </div>

      {selectionError && (
        <p role="alert" className="text-sm text-destructive">
          {selectionError}
        </p>
      )}

      {progress != null && (
        <div className="space-y-1" aria-live="polite">
          <p className="text-xs tabular-nums text-muted-foreground">
            {t("new.upload.inProgress", { percent: progress })}
          </p>
          <Progress value={progress} aria-label={t("new.upload.progressLabel")} />
        </div>
      )}
    </div>
  );
}
