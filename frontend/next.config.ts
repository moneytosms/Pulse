import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  // Repo already has a root CLAUDE.md with the real conventions; don't let
  // `next dev` write a second, generic one into frontend/.
  agentRules: false,
};

export default withNextIntl(nextConfig);
