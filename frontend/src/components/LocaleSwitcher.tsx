"use client";

import { useTransition } from "react";
import { useLocale, useTranslations } from "next-intl";
import { LanguagesIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { api } from "@/lib/api";

// Each language labelled in its own name, so a reader can always find their
// own regardless of the language the page is currently in.
const AUTONYMS: Record<string, string> = {
  en: "English",
  hi: "हिन्दी",
  ta: "தமிழ்",
  ml: "മലയാളം",
};

// EN / HI / TA / ML. Preserves the current path (next-intl navigation strips
// and re-adds the locale prefix) and the query string. Also persists the
// choice for a signed-in Patient; any other visitor's 401/403 is ignored.
export function LocaleSwitcher() {
  const t = useTranslations("locale");
  const activeLocale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          aria-label={t("label")}
          disabled={isPending}
        >
          <LanguagesIcon />
          <span lang={activeLocale}>
            {AUTONYMS[activeLocale] ?? activeLocale}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{t("label")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={activeLocale}
          onValueChange={(locale) =>
            startTransition(() => {
              api.put("/users/me/locale", { locale }).catch(() => {});
              router.replace(pathname, { locale });
            })
          }
        >
          {routing.locales.map((locale) => (
            <DropdownMenuRadioItem key={locale} value={locale} lang={locale}>
              {AUTONYMS[locale] ?? locale}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
