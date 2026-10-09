"use client";

import { useId } from "react";
import type { ComponentProps } from "react";
import { Label } from "@/components/ui/label";

/** Native select for compact query filters, with a persistent accessible label. */
export function SelectFilter({
  label,
  children,
  ...props
}: ComponentProps<"select"> & { label: string }) {
  const id = useId();
  return (
    <div className="min-w-0 space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        className="h-11 min-w-0 w-full rounded-lg border border-input bg-background px-3 text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring sm:h-8 sm:text-sm"
        {...props}
      >
        {children}
      </select>
    </div>
  );
}
