"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import {
  ActivityIcon,
  LogOutIcon,
  MenuIcon,
  MoonIcon,
  SunIcon,
  UserIcon,
} from "lucide-react";
import { LocaleSwitcher } from "@/components/LocaleSwitcher";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api";
import type { Me, Role } from "@/lib/auth";
import { cn } from "@/lib/utils";

type NavKey =
  | "timeline"
  | "consent"
  | "audit"
  | "notifications"
  | "analytics"
  | "profile"
  | "patients"
  | "admin"
  | "duplicates";

const NAV: Record<Role, { key: NavKey; href: string }[]> = {
  PATIENT: [
    { key: "timeline", href: "/timeline" },
    { key: "consent", href: "/consent" },
    { key: "audit", href: "/audit" },
    { key: "analytics", href: "/analytics" },
    { key: "notifications", href: "/notifications" },
    { key: "profile", href: "/profile" },
  ],
  CLINICIAN: [{ key: "patients", href: "/clinician" }],
  PROVIDER_STAFF: [{ key: "patients", href: "/clinician" }],
  ADMINISTRATOR: [
    { key: "admin", href: "/admin" },
    { key: "duplicates", href: "/admin/duplicates" },
  ],
};

// Global chrome. Role comes from /auth/me on each pathname change (a login or
// logout navigates), so the nav never outlives the session it was built for.
// Any failure (401 on public pages included) renders the signed-out header.
export function AppHeader() {
  const t = useTranslations();
  const pathname = usePathname();
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const [me, setMe] = useState<Me | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .get<Me>("/auth/me")
      .then((m) => active && setMe(m))
      .catch(() => active && setMe(null));
    return () => {
      active = false;
    };
  }, [pathname]);

  const links = me ? NAV[me.role] : [];
  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  async function signOut() {
    await api.post("/auth/logout").catch(() => {});
    setMe(null);
    router.replace("/login");
  }

  const navLinks = (onNavigate?: () => void) =>
    links.map(({ key, href }) => (
      <Button
        key={href}
        asChild
        variant="ghost"
        size="sm"
        className={cn(
          "justify-start",
          isActive(href)
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground",
        )}
      >
        <Link
          href={href}
          aria-current={isActive(href) ? "page" : undefined}
          onClick={onNavigate}
        >
          {t(`nav.${key}`)}
        </Link>
      </Button>
    ));

  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4">
        {links.length > 0 && (
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="md:hidden"
                aria-label={t("nav.openMenu")}
              >
                <MenuIcon />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72">
              <SheetHeader>
                <SheetTitle>{t("app.name")}</SheetTitle>
              </SheetHeader>
              <nav
                aria-label={t("nav.label")}
                className="flex flex-col gap-1 px-4"
              >
                {navLinks(() => setMenuOpen(false))}
              </nav>
            </SheetContent>
          </Sheet>
        )}

        <Link
          href="/"
          className="flex items-center gap-2 font-semibold tracking-tight"
        >
          <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <ActivityIcon className="size-4" strokeWidth={2.5} />
          </span>
          {t("app.name")}
        </Link>

        {links.length > 0 && (
          <nav
            aria-label={t("nav.label")}
            className="hidden items-center gap-1 md:flex"
          >
            {navLinks()}
          </nav>
        )}

        <div className="ml-auto flex items-center gap-1">
          <LocaleSwitcher />
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("nav.toggleTheme")}
            onClick={() =>
              setTheme(resolvedTheme === "dark" ? "light" : "dark")
            }
          >
            <SunIcon className="dark:hidden" />
            <MoonIcon className="hidden dark:block" />
          </Button>
          {me ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t("nav.account")}
                >
                  <UserIcon />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel className="truncate font-normal text-muted-foreground">
                  {me.email}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={signOut}>
                  <LogOutIcon />
                  {t("nav.signOut")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            pathname !== "/login" && (
              <Button asChild size="sm">
                <Link href="/login">{t("nav.signIn")}</Link>
              </Button>
            )
          )}
        </div>
      </div>
    </header>
  );
}
