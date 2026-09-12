"use client";

import { Checkbox as RadixCheckbox } from "radix-ui";
import { cn } from "@/lib/cn";

interface CheckboxProps {
  id?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  "aria-describedby"?: string;
}

// Wrapped Radix Checkbox. Used for the consent scope picker's entry-type
// list — a group of these, never a per-entry toggle
// (.claude/rules/frontend.md, docs/domain-model.md: scope is entry-type +
// date window only) — and for a read-only preference display when no write
// endpoint exists yet (`disabled`).
export function Checkbox({ id, checked, onCheckedChange, disabled, ...aria }: CheckboxProps) {
  return (
    <RadixCheckbox.Root
      id={id}
      checked={checked}
      disabled={disabled}
      onCheckedChange={(value) => onCheckedChange(value === true)}
      {...aria}
      className={cn(
        "flex size-5 shrink-0 items-center justify-center rounded border border-border-strong bg-surface",
        "outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-1",
        "focus-visible:ring-offset-background data-[state=checked]:border-accent data-[state=checked]:bg-accent",
        "disabled:cursor-not-allowed disabled:opacity-60",
      )}
    >
      <RadixCheckbox.Indicator className="text-accent-contrast">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </RadixCheckbox.Indicator>
    </RadixCheckbox.Root>
  );
}
