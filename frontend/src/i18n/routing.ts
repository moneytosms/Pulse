import { defineRouting } from "next-intl/routing";

// Full target is four locales (en, hi, ta, ml) per CONTEXT.md.
// Phase 0 stubs only en + hi; add ta/ml once message files exist.
export const routing = defineRouting({
  locales: ["en", "hi"],
  defaultLocale: "en",
});
