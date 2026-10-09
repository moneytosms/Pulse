// Regression coverage for the frontend functional review. Synthetic API fixtures only.
import { expect, test, type Page, type Route } from "@playwright/test";
import type { LabTrendPoint } from "../src/lib/analytics";
const PID = "22222222-2222-2222-2222-222222222222";
const EID = "33333333-3333-3333-3333-333333333333";
const RID = "44444444-4444-4444-4444-444444444444";
const me = {
  userId: "staff",
  role: "PROVIDER_STAFF",
  email: "synthetic@example.com",
  emailVerified: true,
};
const profile = {
  id: PID,
  fullName: "Synthetic Patient",
  dateOfBirth: null,
  sex: null,
  phone: null,
  addressLine: null,
  city: null,
  state: null,
  localePreference: "en",
  claimed: true,
};
const entry = {
  id: EID,
  patientId: PID,
  entryType: "CLINICAL_NOTE",
  occurredAt: "2026-08-01T10:00:00Z",
  recordedAt: "2026-08-01T10:01:00Z",
  isCritical: false,
  supersededById: null,
  sourceProviderId: "provider",
  summary: "Synthetic original",
  text: "Synthetic original",
  documents: [],
  supersedesId: null,
  metadata: {},
};
const json = (r: Route, b: unknown, status = 200) =>
  r.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(b),
  });
async function base(page: Page, role = "PATIENT") {
  await page.route("**/api/v1/**", (r) => {
    const p = new URL(r.request().url()).pathname;
    if (p.endsWith("/auth/me")) return json(r, { ...me, role });
    if (p.endsWith("/patients/me")) return json(r, profile);
    if (p.endsWith("/audit-events"))
      return json(r, { items: [], nextCursor: null });
    if (p.endsWith(`/entries/${EID}`)) return json(r, entry);
    return json(r, { error: { code: "NOT_FOUND", message: "not found" } }, 404);
  });
}
test("language switching preserves correction and patient query parameters", async ({
  page,
}) => {
  await base(page, "PROVIDER_STAFF");
  await page.goto(`/en/timeline/new?patientId=${PID}&corrects=${EID}`);
  await expect(
    page.getByRole("heading", { name: "Correct an entry", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Language", exact: true }).click();
  await page.getByRole("menuitemradio", { name: "हिन्दी" }).click();
  await expect(page).toHaveURL(
    new RegExp(`/hi/timeline/new\\?patientId=${PID}&corrects=${EID}$`),
  );
  await expect(page.locator("input[readonly]")).toHaveValue(PID);
  await expect(page.locator("form")).toBeVisible();
});
test("failed logout stays visible with a retry until the session is terminated", async ({
  page,
}) => {
  await base(page);
  let fail = true,
    signedIn = true;
  await page.route("**/api/v1/auth/me", (r) =>
    signedIn
      ? json(r, { ...me, role: "PATIENT" })
      : json(r, { error: { code: "SESSION_EXPIRED" } }, 401),
  );
  await page.route("**/api/v1/auth/logout", (r) => {
    if (fail) return json(r, { error: { code: "GENERIC" } }, 500);
    signedIn = false;
    return r.fulfill({ status: 204 });
  });
  await page.goto("/en/profile");
  await expect(
    page.getByText("Synthetic Patient", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Account", exact: true }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(
    page.getByText(
      "Could not sign out. Try again before leaving this device.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/en\/profile$/);
  fail = false;
  await page
    .getByRole("button", { name: "Retry sign out", exact: true })
    .click();
  await expect(page).toHaveURL(/\/en\/login$/);
  await expect(
    page.getByRole("button", { name: "Account", exact: true }),
  ).toHaveCount(0);
});
test("expired verification recovers through an email-entry resend form", async ({
  page,
}) => {
  await base(page);
  let resent = "";
  await page.route("**/api/v1/auth/verify", (r) =>
    json(r, { error: { code: "VERIFICATION_TOKEN_EXPIRED" } }, 400),
  );
  await page.route("**/api/v1/auth/verify/resend", (r) => {
    resent = r.request().postDataJSON().email;
    return json(r, {}, 202);
  });
  await page.goto("/en/verify?challenge=synthetic&token=synthetic");
  await page
    .getByRole("link", { name: "Resend the confirmation email" })
    .click();
  await page.getByLabel("Email address").fill("synthetic@example.com");
  await page
    .getByRole("button", { name: "Resend the confirmation email", exact: true })
    .click();
  await expect(
    page.getByText("A fresh confirmation email is on its way.", {
      exact: true,
    }),
  ).toBeVisible();
  expect(resent).toBe("synthetic@example.com");
});
test("attachment progress and retry preserve the single persisted correction", async ({
  page,
}) => {
  await base(page, "PROVIDER_STAFF");
  let created = 0,
    uploaded = 0,
    started = false;
  let release!: () => void;
  const held = new Promise<void>((r) => (release = r));
  await page.route(
    `**/api/v1/patients/${PID}/entries/${EID}/corrections`,
    (r) => {
      created++;
      return json(r, { id: RID }, 201);
    },
  );
  await page.route("**/documents", async (r) => {
    uploaded++;
    started = true;
    if (uploaded === 1) {
      await held;
      return json(r, { error: { code: "PAYLOAD_TOO_LARGE" } }, 413);
    }
    expect(new URL(r.request().url()).pathname).toContain(
      `/entries/${RID}/documents`,
    );
    return json(r, { id: "document" }, 201);
  });
  await page.goto(`/en/timeline/new?patientId=${PID}&corrects=${EID}`);
  await expect(page.getByLabel("Note text")).toHaveValue("Synthetic original");
  await page.locator("input[type=file]").setInputFiles({
    name: "synthetic.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4"),
  });
  await page
    .getByRole("button", { name: "File correction", exact: true })
    .click();
  try {
    await expect.poll(() => started).toBe(true);
    await expect(page.getByRole("progressbar")).toBeVisible();
    await expect(
      page.getByText(
        "The entry is saved. Keep this page open while the document uploads.",
        { exact: true },
      ),
    ).toBeVisible();
  } finally {
    release();
  }
  await expect(
    page.getByText(
      "This file is too large — compress or split it and try again.",
    ),
  ).toBeVisible();
  await page.locator("input[type=file]").setInputFiles({
    name: "smaller.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4"),
  });
  await page
    .getByRole("button", { name: "Retry document upload", exact: true })
    .click();
  await expect(
    page.getByText("Document attached.", { exact: true }),
  ).toBeVisible();
  expect(created).toBe(1);
  expect(uploaded).toBe(2);
});
test("delayed load-more is discarded after changing the type filter", async ({
  page,
}) => {
  await base(page);
  const diagnosis = {
    ...entry,
    id: "diagnosis",
    entryType: "DIAGNOSIS",
    summary: "Synthetic diagnosis",
  };
  const lab = {
    ...entry,
    id: "lab",
    entryType: "LAB_REPORT",
    summary: "Synthetic lab",
  };
  let started = false;
  let release!: () => void;
  const held = new Promise<void>((r) => (release = r));
  await page.route(`**/api/v1/patients/${PID}/entries?*`, async (r) => {
    const q = new URL(r.request().url()).searchParams;
    if (q.has("cursor")) {
      started = true;
      await held;
      return json(r, {
        items: [{ ...diagnosis, id: "stale", summary: "Stale diagnosis page" }],
        nextCursor: "all-third-page",
      }).catch(() => undefined);
    }
    return json(r, {
      items: q.has("entryType") ? [lab] : [diagnosis],
      nextCursor: q.has("entryType") ? null : "all-second-page",
    });
  });
  await page.goto("/en/timeline");
  await page.getByRole("button", { name: "Load more", exact: true }).click();
  try {
    await expect.poll(() => started).toBe(true);
    await page.getByRole("combobox", { name: "Filter by type" }).click();
    await page.getByRole("option", { name: "Lab report", exact: true }).click();
    await expect(
      page.getByText("Synthetic lab", { exact: true }),
    ).toBeVisible();
  } finally {
    release();
  }
  await page.waitForTimeout(150);
  await expect(
    page.getByText("Stale diagnosis page", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Load more", exact: true }),
  ).toHaveCount(0);
});
test("patient and clinician entry details show critical and superseded status", async ({
  page,
}) => {
  await base(page, "CLINICIAN");
  await page.route(`**/api/v1/entries/${EID}`, (r) =>
    json(r, { ...entry, isCritical: true, supersededById: RID }),
  );
  for (const path of [
    `/en/timeline/${EID}`,
    `/en/patients/${PID}/records/${EID}`,
  ]) {
    await page.goto(path);
    await expect(
      page.getByText("Synthetic original", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Critical", { exact: true })).toBeVisible();
    await expect(page.locator(`a[href*="${RID}"]`)).toBeVisible();
    await expect(
      page.getByText("This entry has been superseded by a correction.", {
        exact: true,
      }),
    ).toBeVisible();
  }
});
test("initial patient lookup can be retried on timeline, profile and analytics", async ({
  page,
}) => {
  await base(page);
  let available = false;
  await page.route("**/api/v1/patients/me", (r) =>
    available ? json(r, profile) : json(r, { error: { code: "GENERIC" } }, 503),
  );
  await page.route(`**/api/v1/patients/${PID}/entries?*`, (r) =>
    json(r, { items: [entry], nextCursor: null }),
  );
  await page.route("**/api/v1/patients/*/analytics/*", (r) => json(r, []));
  for (const path of ["timeline", "profile", "analytics"]) {
    available = false;
    await page.goto(`/en/${path}`);
    await expect(
      page.getByRole("button", { name: "Try again", exact: true }),
    ).toBeVisible();
    available = true;
    await page.getByRole("button", { name: "Try again", exact: true }).click();
    if (path === "timeline")
      await expect(
        page.getByText("Synthetic original", { exact: true }),
      ).toBeVisible();
    if (path === "profile")
      await expect(
        page.getByText("Synthetic Patient", { exact: true }),
      ).toBeVisible();
    if (path === "analytics")
      await expect(
        page.getByText("Recorded prescriptions", { exact: true }).first(),
      ).toBeVisible();
  }
});
test("clinician patient discovery loads the next consented-patient page", async ({
  page,
}) => {
  await base(page, "CLINICIAN");
  await page.route("**/api/v1/consents/granted-to-me*", (r) => {
    const more = new URL(r.request().url()).searchParams.has("cursor");
    return json(r, {
      items: [
        {
          patientId: more ? RID : PID,
          fullName: more
            ? "Next synthetic patient"
            : "Synthetic granted patient",
          expiresAt: "2027-01-01T00:00:00Z",
        },
      ],
      nextCursor: more ? null : "more-granted-patients",
    });
  });
  await page.goto("/en/clinician");
  await expect(
    page.getByText("Synthetic granted patient", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Load more patients", exact: true })
    .click();
  await expect(
    page.getByText("Next synthetic patient", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Load more patients", exact: true }),
  ).toHaveCount(0);
});
test("emergency banner queries recent emergency events directly", async ({
  page,
}) => {
  await base(page);
  await page.route("**/api/v1/audit-events?*", (r) => {
    const q = new URL(r.request().url()).searchParams;
    if (q.get("action") !== "BREAK_GLASS_ACCESS" || !q.get("since"))
      return json(r, { items: [], nextCursor: null });
    expect(q.get("limit")).toBe("1");
    return json(r, {
      items: [
        {
          id: "emergency",
          action: "BREAK_GLASS_ACCESS",
          occurredAt: new Date().toISOString(),
        },
      ],
      nextCursor: null,
    });
  });
  await page.route(`**/api/v1/patients/${PID}/entries?*`, (r) =>
    json(r, { items: [entry], nextCursor: null }),
  );
  await page.goto("/en/timeline");
  await expect(
    page.getByText("Emergency access to your record", { exact: true }),
  ).toBeVisible();
});
test("patient header fits mobile and tablet widths in every locale", async ({
  page,
}) => {
  await base(page);
  const results = [];
  for (const locale of ["en", "hi", "ta", "ml"]) {
    await page.goto(`/${locale}/profile`);
    await expect(
      page.getByText("Synthetic Patient", { exact: true }),
    ).toBeVisible();
    for (const width of [390, 768, 1024, 1280]) {
      await page.setViewportSize({ width, height: 844 });
      await page.waitForTimeout(100);
      results.push(
        await page.evaluate(
          ({ locale, width }) => {
            const account = document
              .querySelector("header button:last-child")
              ?.getBoundingClientRect();
            return {
              locale,
              width,
              scrollWidth: document.documentElement.scrollWidth,
              clientWidth: document.documentElement.clientWidth,
              headerWidth: document.querySelector("header")?.scrollWidth,
              accountRight: account?.right,
            };
          },
          { locale, width },
        ),
      );
    }
  }
  for (const result of results)
    expect(
      result.scrollWidth,
      `${result.locale} at ${result.width}px`,
    ).toBeLessThanOrEqual(result.clientWidth);
});
test("mobile menu supports keyboard access and theme toggle updates the root", async ({
  page,
}) => {
  await base(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/en/profile");
  await expect(
    page.getByText("Synthetic Patient", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open menu", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("dialog")
    .getByRole("link", { name: "Profile", exact: true })
    .focus();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Toggle theme", exact: true }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
});
test("analytics preserves qualitative lab results and separates measurement units", async ({
  page,
}) => {
  await base(page);
  let points: LabTrendPoint[] = [
    {
      occurredAt: "2026-08-01T10:00:00Z",
      valueNumeric: null,
      valueText: "Synthetic qualitative result",
      unit: null,
      referenceLow: null,
      referenceHigh: null,
      isAbnormal: null,
    },
  ];
  await page.route("**/api/v1/patients/*/analytics/*", (r) => {
    const url = new URL(r.request().url());
    if (url.pathname.endsWith("/lab-tests"))
      return json(r, [
        {
          codeSystem: "LOINC",
          code: "synthetic",
          displayName: "Synthetic test",
        },
      ]);
    if (url.pathname.endsWith("/lab-trend")) return json(r, points);
    return json(r, []);
  });
  await page.goto("/en/analytics");
  await expect(
    page.getByText("Synthetic qualitative result", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".recharts-line-dots circle")).toHaveCount(0);
  points = [
    {
      occurredAt: "2026-08-01T10:00:00Z",
      valueNumeric: 100,
      valueText: null,
      unit: "mg/dL",
      referenceLow: null,
      referenceHigh: null,
      isAbnormal: null,
    },
    {
      occurredAt: "2026-08-02T10:00:00Z",
      valueNumeric: 5.6,
      valueText: null,
      unit: "mmol/L",
      referenceLow: null,
      referenceHigh: null,
      isAbnormal: null,
    },
    {
      occurredAt: "2026-08-03T10:00:00Z",
      valueNumeric: 0,
      valueText: null,
      unit: "mg/dL",
      referenceLow: 1,
      referenceHigh: 10,
      isAbnormal: true,
    },
  ];
  await page.reload();
  await expect(page.locator("[data-testid=lab-numeric-series]")).toHaveCount(2);
  await expect(page.getByRole("table", { name: "Lab results" })).toContainText(
    "mg/dL",
  );
  await expect(page.getByRole("table", { name: "Lab results" })).toContainText(
    "mmol/L",
  );
  await expect(
    page
      .getByRole("table", { name: "Lab results" })
      .getByRole("cell", { name: "0", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("below reference range", { exact: true }),
  ).toBeVisible();
});

test("language switching keeps verification parameters and can retain an unsaved correction", async ({
  page,
}) => {
  await base(page, "PROVIDER_STAFF");
  let verified = 0;
  await page.route("**/api/v1/auth/verify", (r) =>
    ++verified === 1
      ? json(r, {}, 200)
      : json(r, { error: { code: "VERIFICATION_TOKEN_EXPIRED" } }, 400),
  );
  await page.goto(
    "/en/verify?challenge=synthetic&token=synthetic&extra=1&extra=2",
  );
  await expect(
    page.getByRole("link", { name: "Continue to sign in" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Language", exact: true }).click();
  await page.getByRole("menuitemradio", { name: "हिन्दी" }).click();
  await expect(page).toHaveURL(
    /\/hi\/verify\?challenge=synthetic&token=synthetic&extra=1&extra=2$/,
  );
  await expect(
    page.getByText(
      "आपके ईमेल पते की पुष्टि हो गई है। अब आप साइन इन कर सकते हैं।",
      { exact: true },
    ),
  ).toBeVisible();
  expect(verified).toBe(1);
  await page.goto(`/en/timeline/new?patientId=${PID}&corrects=${EID}`);
  await expect(page.getByLabel("Note text")).toHaveValue("Synthetic original");
  await page.getByLabel("Note text").fill("Unsaved synthetic change");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "Language", exact: true }).click();
  await page.getByRole("menuitemradio", { name: "हिन्दी" }).click();
  await expect(page).toHaveURL(
    new RegExp(`/en/timeline/new\\?patientId=${PID}&corrects=${EID}$`),
  );
  await expect(page.getByLabel("Note text")).toHaveValue(
    "Unsaved synthetic change",
  );
});

test("temporary verification failure offers retry instead of an invalid-token claim", async ({
  page,
}) => {
  await base(page);
  let available = false;
  await page.route("**/api/v1/auth/verify", (r) =>
    available ? json(r, {}, 200) : json(r, { error: { code: "GENERIC" } }, 503),
  );
  await page.goto("/en/verify?challenge=synthetic&token=synthetic");
  await expect(
    page.getByText("Confirmation is temporarily unavailable. Try again.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("This confirmation link is not valid.", { exact: true }),
  ).toHaveCount(0);
  available = true;
  await page
    .getByRole("button", { name: "Retry confirmation", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Continue to sign in" }),
  ).toBeVisible();
});

test("staff attach a document to an existing entry without creating another entry", async ({
  page,
}) => {
  await base(page, "PROVIDER_STAFF");
  let posts = 0;
  await page.route("**/api/v1/patients/**", (r) => {
    expect(r.request().method()).toBe("POST");
    expect(new URL(r.request().url()).pathname).toBe(
      `/api/v1/patients/${PID}/entries/${EID}/documents`,
    );
    posts++;
    return json(
      r,
      {
        id: "doc",
        entryId: EID,
        filename: "synthetic.pdf",
        mimeType: "application/pdf",
        sizeBytes: 8,
        checksumSha256: "synthetic",
        uploadedAt: "2026-08-01T10:00:00Z",
      },
      201,
    );
  });
  await page.goto(`/en/patients/${PID}/records/${EID}`);
  await expect(
    page.getByText("Synthetic original", { exact: true }),
  ).toBeVisible();
  await page.locator("input[type=file]").setInputFiles({
    name: "synthetic.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4"),
  });
  await page
    .getByRole("button", { name: "Attach document", exact: true })
    .click();
  await expect(
    page.getByText("Document attached.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "View", exact: true }),
  ).toBeVisible();
  expect(posts).toBe(1);
});

test("switching entry types submits only the visible subtype while preserving its draft", async ({
  page,
}) => {
  await base(page, "PROVIDER_STAFF");
  let payload: Record<string, unknown> | undefined;
  await page.route(`**/api/v1/patients/${PID}/entries`, (r) => {
    payload = r.request().postDataJSON();
    return json(r, { id: RID }, 201);
  });
  await page.goto(`/en/timeline/new?patientId=${PID}`);
  await page.getByRole("combobox", { name: "Entry type", exact: true }).click();
  await page.getByRole("option", { name: "Lab report", exact: true }).click();
  await page
    .getByLabel("Occurred at", { exact: true })
    .fill("2026-08-01T10:00");
  await page.getByLabel("Code system", { exact: true }).fill("LOINC");
  await page.getByLabel("Code", { exact: true }).fill("synthetic-test");
  await page.getByLabel("Display name", { exact: true }).fill("Synthetic lab");
  await page.getByLabel("Result (numeric)", { exact: true }).fill("5.6");
  await page.getByLabel("Reference range — low", { exact: true }).fill("10");
  await page.getByLabel("Reference range — high", { exact: true }).fill("1");
  await page.getByRole("combobox", { name: "Entry type", exact: true }).click();
  await page
    .getByRole("option", { name: "Clinical note", exact: true })
    .click();
  await page.getByLabel("Note text", { exact: true }).fill("Synthetic note");
  await page.getByRole("combobox", { name: "Entry type", exact: true }).click();
  await page.getByRole("option", { name: "Lab report", exact: true }).click();
  await expect(
    page.getByLabel("Result (numeric)", { exact: true }),
  ).toHaveValue("5.6");
  await page.getByRole("combobox", { name: "Entry type", exact: true }).click();
  await page
    .getByRole("option", { name: "Clinical note", exact: true })
    .click();
  await page.getByRole("button", { name: "File entry", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "View entry", exact: true }),
  ).toBeVisible();
  expect(payload).toMatchObject({
    entryType: "CLINICAL_NOTE",
    text: "Synthetic note",
  });
  for (const key of [
    "codeSystem",
    "code",
    "displayName",
    "valueNumeric",
    "valueText",
    "unit",
    "referenceLow",
    "referenceHigh",
    "medicationName",
    "dosage",
    "frequency",
    "route",
  ]) {
    expect(payload?.[key], key).toBeNull();
  }
});

test("entry fields stay locked during save and recover unchanged after a failure", async ({
  page,
}) => {
  await base(page, "PROVIDER_STAFF");
  let started = false;
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let posts = 0;
  await page.route(`**/api/v1/patients/${PID}/entries`, async (r) => {
    posts++;
    if (posts === 1) {
      started = true;
      await held;
      return json(r, { error: { code: "GENERIC" } }, 503);
    }
    return json(r, { id: RID }, 201);
  });
  await page.goto(`/en/timeline/new?patientId=${PID}`);
  await page.getByRole("combobox", { name: "Entry type", exact: true }).click();
  await page
    .getByRole("option", { name: "Clinical note", exact: true })
    .click();
  await page
    .getByLabel("Occurred at", { exact: true })
    .fill("2026-08-01T10:00");
  await page
    .getByLabel("Note text", { exact: true })
    .fill("Synthetic pending note");
  await page.getByRole("button", { name: "File entry", exact: true }).click();
  try {
    await expect.poll(() => started).toBe(true);
    await expect(page.getByLabel("Patient ID", { exact: true })).toBeDisabled();
    await expect(
      page.getByRole("combobox", { name: "Entry type", exact: true }),
    ).toBeDisabled();
    await expect(
      page.getByRole("checkbox", { name: "Mark as critical", exact: true }),
    ).toBeDisabled();
    await expect(page.getByLabel("Note text", { exact: true })).toBeDisabled();
  } finally {
    release();
  }
  await expect(page.getByLabel("Patient ID", { exact: true })).toBeEnabled();
  await expect(page.getByLabel("Note text", { exact: true })).toHaveValue(
    "Synthetic pending note",
  );
  await expect(page.locator('[data-slot="alert"]')).toBeVisible();
  await page.getByRole("button", { name: "File entry", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "View entry", exact: true }),
  ).toHaveAttribute("href", `/en/patients/${PID}/records/${RID}`);
  expect(posts).toBe(2);
});

test("entry detail rejects a different patient in the route", async ({
  page,
}) => {
  await base(page, "PROVIDER_STAFF");
  await page.goto(`/en/patients/${PID}/records/${EID}`);
  await expect(
    page.getByText("Synthetic original", { exact: true }),
  ).toBeVisible();
  await page.goto(`/en/patients/${RID}/records/${EID}`);
  await expect(
    page.getByText("Record not found", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Synthetic original", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Attach document", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Correct this entry", exact: true }),
  ).toHaveCount(0);
});

test("prescription correction exposes and preserves its existing optional coding", async ({
  page,
}) => {
  await base(page, "PROVIDER_STAFF");
  await page.route(`**/api/v1/entries/${EID}`, (r) =>
    json(r, {
      ...entry,
      entryType: "PRESCRIPTION",
      codeSystem: "RxNorm",
      code: "synthetic-medication",
      displayName: "Synthetic coded medication",
      medicationName: "Synthetic medication",
      dosage: "Synthetic dosage",
      text: null,
    }),
  );
  let payload: Record<string, unknown> | undefined;
  await page.route(
    `**/api/v1/patients/${PID}/entries/${EID}/corrections`,
    (r) => {
      payload = r.request().postDataJSON();
      return json(r, { id: RID }, 201);
    },
  );
  await page.goto(`/en/timeline/new?patientId=${PID}&corrects=${EID}`);
  await expect(page.getByLabel("Code system", { exact: true })).toHaveValue(
    "RxNorm",
  );
  await expect(page.getByLabel("Code", { exact: true })).toHaveValue(
    "synthetic-medication",
  );
  await page
    .getByLabel("Dosage", { exact: true })
    .fill("Synthetic corrected dosage");
  await page
    .getByRole("button", { name: "File correction", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "View entry", exact: true }),
  ).toBeVisible();
  expect(payload).toMatchObject({
    entryType: "PRESCRIPTION",
    codeSystem: "RxNorm",
    code: "synthetic-medication",
    displayName: "Synthetic coded medication",
    medicationName: "Synthetic medication",
    dosage: "Synthetic corrected dosage",
    valueNumeric: null,
    referenceLow: null,
    referenceHigh: null,
    text: null,
  });
});
