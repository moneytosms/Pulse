import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

// Matches a hex colour literal: #rgb, #rgba, #rrggbb, #rrggbbaa.
const HEX_COLOUR = String.raw`/#(?:[0-9a-fA-F]{3,4}){1,2}\b/`;

const eslintConfig = [
  ...nextCoreWebVitals,
  ...nextTypeScript,
  {
    // eslint-config-next@16.3.2 bundles eslint-plugin-react, whose React-version
    // auto-detect calls a context API that ESLint 10 removed
    // (`contextOrFilename.getFilename is not a function`). Pinning the version
    // string skips the detection and the broken code path.
    settings: { react: { version: "19.2.0" } },
  },
  {
    // docs/design-direction.md: components write semantic tokens
    // (`text-critical`, `bg-surface`) — never a hex, never `red-500`. Raw colour
    // values live only in src/styles/tokens.css.
    files: ["src/components/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: `Literal[value=${HEX_COLOUR}]`,
          message:
            "No hex colour literals in components. Use a semantic token utility (see src/app/globals.css).",
        },
        {
          selector: `TemplateElement[value.raw=${HEX_COLOUR}]`,
          message:
            "No hex colour literals in components. Use a semantic token utility (see src/app/globals.css).",
        },
      ],
    },
  },
  {
    ignores: [
      ".next/**",
      "next-env.d.ts",
      "e2e/**",
      "playwright.config.ts",
      "playwright-report/**",
      "test-results/**",
    ],
  },
];

export default eslintConfig;
