import { hasLocale } from "next-intl";
import { getRequestConfig } from "next-intl/server";
import { routing } from "./routing";

// One catalog file per feature per locale, so four people editing translations
// do not conflict on every PR (.claude/rules/frontend.md). `common.json` is
// spread at the root (it groups its own keys: `app`, `home`, `locale`, …);
// every other file is mounted under a namespace matching its filename.
//
// Static imports (not a dynamic `import(\`...${ns}\`)`) so the bundler resolves
// every catalog at build time and a missing file is a build error.
import enCommon from "./messages/en/common.json";
import enAuth from "./messages/en/auth.json";
import enAudit from "./messages/en/audit.json";
import enConsent from "./messages/en/consent.json";
import enEntry from "./messages/en/entry.json";
import enErrors from "./messages/en/errors.json";
import enProfile from "./messages/en/profile.json";
import enTimeline from "./messages/en/timeline.json";
import hiCommon from "./messages/hi/common.json";
import hiAuth from "./messages/hi/auth.json";
import hiAudit from "./messages/hi/audit.json";
import hiConsent from "./messages/hi/consent.json";
import hiEntry from "./messages/hi/entry.json";
import hiErrors from "./messages/hi/errors.json";
import hiProfile from "./messages/hi/profile.json";
import hiTimeline from "./messages/hi/timeline.json";
import taCommon from "./messages/ta/common.json";
import taAuth from "./messages/ta/auth.json";
import taAudit from "./messages/ta/audit.json";
import taConsent from "./messages/ta/consent.json";
import taEntry from "./messages/ta/entry.json";
import taErrors from "./messages/ta/errors.json";
import taProfile from "./messages/ta/profile.json";
import taTimeline from "./messages/ta/timeline.json";
import mlCommon from "./messages/ml/common.json";
import mlAuth from "./messages/ml/auth.json";
import mlAudit from "./messages/ml/audit.json";
import mlConsent from "./messages/ml/consent.json";
import mlEntry from "./messages/ml/entry.json";
import mlErrors from "./messages/ml/errors.json";
import mlProfile from "./messages/ml/profile.json";
import mlTimeline from "./messages/ml/timeline.json";

type Catalog = Record<string, unknown>;

const CATALOGS: Record<string, Catalog> = {
  en: {
    ...enCommon,
    auth: enAuth,
    audit: enAudit,
    consent: enConsent,
    entry: enEntry,
    errors: enErrors,
    profile: enProfile,
    timeline: enTimeline,
  },
  hi: {
    ...hiCommon,
    auth: hiAuth,
    audit: hiAudit,
    consent: hiConsent,
    entry: hiEntry,
    errors: hiErrors,
    profile: hiProfile,
    timeline: hiTimeline,
  },
  ta: {
    ...taCommon,
    auth: taAuth,
    audit: taAudit,
    consent: taConsent,
    entry: taEntry,
    errors: taErrors,
    profile: taProfile,
    timeline: taTimeline,
  },
  ml: {
    ...mlCommon,
    auth: mlAuth,
    audit: mlAudit,
    consent: mlConsent,
    entry: mlEntry,
    errors: mlErrors,
    profile: mlProfile,
    timeline: mlTimeline,
  },
};

// A catalog awaiting translation ships every key with an empty-string value, so
// translators see the full structure (P2.10). next-intl only raises
// MISSING_MESSAGE for a key that is entirely absent -- a key present as "" is a
// successful lookup that renders blank. That would make an untranslated locale
// invisible in dev and CI, which is the one thing the guard below exists to
// prevent, so empty leaves are dropped before the catalog is handed over: they
// then throw in dev/CI and fall back to English in production.
function pruneEmpty(catalog: Catalog): Catalog {
  const out: Catalog = {};
  for (const [key, value] of Object.entries(catalog)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const nested = pruneEmpty(value as Catalog);
      if (Object.keys(nested).length > 0) out[key] = nested;
    } else if (value !== "") {
      out[key] = value;
    }
  }
  return out;
}

function mergeCatalogs(base: Catalog, override: Catalog): Catalog {
  const out: Catalog = { ...base };
  for (const [key, value] of Object.entries(override)) {
    out[key] =
      value && typeof value === "object" && !Array.isArray(value)
        ? { ...(base[key] as object), ...(value as object) }
        : value;
  }
  return out;
}

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested)
    ? requested
    : routing.defaultLocale;

  const isProduction = process.env.NODE_ENV === "production";

  // Dev and CI: use only the requested locale, so a missing key throws.
  // Production: layer the requested locale over an English base so a gap
  // degrades to English rather than crashing a live page.
  const catalog = pruneEmpty(CATALOGS[locale]);
  const messages =
    isProduction && locale !== routing.defaultLocale
      ? mergeCatalogs(CATALOGS[routing.defaultLocale], catalog)
      : catalog;

  return {
    locale,
    messages,
    onError(error) {
      if (error.code === "MISSING_MESSAGE" && !isProduction) {
        // Fail loud in dev and CI — a missing Hindi string must not reach review.
        throw error;
      }
      console.error(error);
    },
  };
});
