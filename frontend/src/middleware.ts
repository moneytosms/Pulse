import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  // Must exclude /api (Caddy routes it to FastAPI on the same origin — see
  // docs/tech-stack.md and ADR-0012), _next, _vercel, and any file with an extension.
  matcher: "/((?!api|_next|_vercel|.*\\..*).*)",
};
