import type { Metadata } from "next";
import type { ReactNode } from "react";
import { hasLocale, NextIntlClientProvider, useTranslations } from "next-intl";
import { notFound } from "next/navigation";
import { ThemeProvider } from "next-themes";
import { AppHeader } from "@/components/AppHeader";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { routing } from "@/i18n/routing";
import "../globals.css";
import "../fonts";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export const metadata: Metadata = {
  title: "Pulse",
};

type Props = {
  children: ReactNode;
  params: Promise<{ locale: string }>;
};

// Sync Server Component so next-intl's `useTranslations` is available for the
// chrome (skip link, footer). The header is a client component (session-aware).
function Shell({ children }: { children: ReactNode }) {
  const t = useTranslations("app");
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        {t("skipToContent")}
      </a>
      <div className="flex min-h-dvh flex-col">
        <AppHeader />
        <main
          id="main"
          className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:py-10"
        >
          {children}
        </main>
        <footer className="border-t">
          <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-5 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
            <p>
              {t("name")} — {t("tagline")}
            </p>
            <p>{t("confidentialityNote")}</p>
          </div>
        </footer>
      </div>
    </>
  );
}

export default async function LocaleLayout({ children, params }: Props) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) {
    notFound();
  }

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="min-h-dvh">
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          <NextIntlClientProvider>
            <TooltipProvider>
              <Shell>{children}</Shell>
              <Toaster richColors />
            </TooltipProvider>
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
