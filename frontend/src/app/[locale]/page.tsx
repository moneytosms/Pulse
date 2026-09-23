import { useTranslations } from "next-intl";
import { ActivityIcon, EyeIcon, NotebookPenIcon, ShieldCheckIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "@/i18n/navigation";

// Home = the product's spine in three cards: the lifelong history, consent
// the patient controls, and the audit log that keeps both honest. Everything
// below is interface chrome — clinical data never appears on this page.
export default function HomePage() {
  const t = useTranslations("home");

  const features = [
    { icon: NotebookPenIcon, title: t("features.history.title"), body: t("features.history.body") },
    { icon: ShieldCheckIcon, title: t("features.consent.title"), body: t("features.consent.body") },
    { icon: EyeIcon, title: t("features.audit.title"), body: t("features.audit.body") },
  ] as const;

  return (
    <div className="animate-in fade-in-0 slide-in-from-bottom-1 space-y-12 duration-300 motion-reduce:animate-none">
      <section className="mx-auto max-w-2xl space-y-5 pt-6 text-center sm:pt-12">
        <Badge variant="outline" className="gap-1.5 text-primary">
          <ActivityIcon className="size-3.5" />
          {t("badge")}
        </Badge>
        <h1 className="text-balance text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          {t("title")}
        </h1>
        <p className="text-pretty text-base text-muted-foreground sm:text-lg">
          {t("description")}
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
          <Button asChild className="h-11 min-w-40">
            <Link href="/register">{t("registerCta")}</Link>
          </Button>
          <Button asChild variant="outline" className="h-11 min-w-40">
            <Link href="/login">{t("loginCta")}</Link>
          </Button>
        </div>
      </section>

      <section aria-label={t("features.label")} className="grid gap-4 sm:grid-cols-3">
        {features.map(({ icon: Icon, title, body }) => (
          <Card key={title}>
            <CardHeader>
              <span className="mb-2 flex size-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Icon className="size-4" />
              </span>
              <CardTitle className="text-base">{title}</CardTitle>
              <CardDescription>{body}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </section>
    </div>
  );
}
