"use client";

// Root error boundary. Renders outside the [locale] segment (no params, no
// i18n context available), so this stays plain — see
// https://nextjs.org/docs/app/api-reference/file-conventions/error
export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <h1>Something went wrong</h1>
        <button onClick={reset}>Try again</button>
      </body>
    </html>
  );
}
