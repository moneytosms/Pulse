import { expect, test, type Page, type Route } from "@playwright/test";

const PID = "22222222-2222-2222-2222-222222222222";
const CID = "33333333-3333-3333-3333-333333333333";
const expiry = new Date(Date.now() + 7 * 86_400_000).toISOString();
const consent = {
  id: CID,
  patientId: PID,
  granteeUserId: "clinician",
  granteeName: "clinician@example.com",
  entryTypes: null,
  fromDate: null,
  toDate: null,
  purpose: "TREATMENT",
  purposeText: null,
  status: "ACTIVE",
  expiresAt: expiry,
  grantedAt: new Date().toISOString(),
  revokedAt: null,
  revocationReason: null,
};
const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
async function base(page: Page) {
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me"))
      return json(route, {
        userId: "patient",
        email: "patient@example.com",
        role: "PATIENT",
        emailVerified: true,
      });
    if (path.endsWith("/patients/me")) return json(route, { id: PID });
    if (path.endsWith("/clinicians/lookup"))
      return json(route, {
        userId: "clinician",
        email: "clinician@example.com",
      });
    if (path.endsWith("/entry-providers"))
      return json(route, [{ id: "provider", name: "Synthetic Clinic" }]);
    if (path.endsWith("/auth/step-up")) return json(route, {});
    return json(route, { items: [], nextCursor: null });
  });
}
async function grantDetails(page: Page) {
  await page
    .getByLabel("Clinician email", { exact: true })
    .fill("clinician@example.com");
  await page.getByRole("combobox", { name: "Purpose", exact: true }).click();
  await page.getByRole("option", { name: "Treatment", exact: true }).click();
  await page
    .getByLabel("Access expires", { exact: true })
    .fill(expiry.slice(0, 16));
}

test("an untouched or empty selected scope cannot grant broad access", async ({
  page,
}) => {
  await base(page);
  let writes = 0;
  await page.route("**/api/v1/consents", (route) => {
    if (route.request().method() === "POST") writes++;
    return json(route, consent);
  });
  await page.goto("/en/consent/new");
  await grantDetails(page);
  await page
    .getByRole("button", { name: "Review access", exact: true })
    .click();
  await expect(
    page.getByText("Choose all entry types, or select at least one type."),
  ).toBeVisible();
  await page
    .getByRole("radio", { name: "Choose entry types", exact: true })
    .check();
  await page
    .getByRole("button", { name: "Review access", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Review before sharing" }),
  ).toHaveCount(0);
  expect(writes).toBe(0);
});

test("selected sharing is reviewed before step-up and preserves scope on failed password", async ({
  page,
}) => {
  await base(page);
  let writes = 0;
  let payload: Record<string, unknown> = {};
  await page.route("**/api/v1/consents", (route) => {
    writes++;
    payload = route.request().postDataJSON();
    return json(route, { ...consent, ...payload });
  });
  await page.route("**/api/v1/auth/step-up", (route) =>
    json(
      route,
      route.request().postDataJSON().password === "wrong"
        ? { error: { code: "INVALID_CREDENTIALS" } }
        : {},
      route.request().postDataJSON().password === "wrong" ? 401 : 200,
    ),
  );
  await page.goto("/en/consent/new");
  await grantDetails(page);
  await page
    .getByRole("radio", { name: "Choose entry types", exact: true })
    .check();
  await page.getByRole("checkbox", { name: "Lab report", exact: true }).check();
  await page
    .getByRole("button", { name: "Review access", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Review before sharing" }),
  ).toBeFocused();
  await expect(
    page.getByRole("textbox", { name: "Clinician email", exact: true }),
  ).toHaveCount(0);
  expect(writes).toBe(0);
  await page.getByLabel("Confirm with your password").fill("wrong");
  await page.getByRole("button", { name: "Grant access", exact: true }).click();
  await expect(page.getByText("That password is not correct.")).toBeVisible();
  expect(writes).toBe(0);
  await page.getByLabel("Confirm with your password").fill("correct");
  await page.getByRole("button", { name: "Grant access", exact: true }).click();
  await expect(page.getByText("Access granted", { exact: true })).toBeVisible();
  expect(payload.entryTypes).toEqual(["LAB_REPORT"]);
  expect(writes).toBe(1);
});

test("all types requires a deliberate choice and editing reopens the reviewed form", async ({
  page,
}) => {
  await base(page);
  await page.goto("/en/consent/new");
  await grantDetails(page);
  await page
    .getByRole("radio", { name: "All entry types", exact: true })
    .check();
  await page
    .getByRole("button", { name: "Review access", exact: true })
    .click();
  await expect(
    page.getByText("All entry types", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Edit details" }).click();
  await expect(
    page.getByRole("radio", { name: "All entry types", exact: true }),
  ).toBeChecked();
  await expect(page.getByLabel("Clinician email", { exact: true })).toHaveValue(
    "clinician@example.com",
  );
});

test("current access uses server filtering and keeps revoked history separate", async ({
  page,
}) => {
  await base(page);
  await page.route("**/api/v1/consents?**", (route) => {
    const view = new URL(route.request().url()).searchParams.get("view");
    return json(route, {
      items:
        view === "history"
          ? [
              {
                ...consent,
                status: "REVOKED",
                revokedAt: new Date().toISOString(),
              },
            ]
          : [],
      nextCursor: null,
    });
  });
  await page.goto("/en/consent");
  await expect(
    page.getByText("No one currently has access through your consents"),
  ).toBeVisible();
  await expect(page.getByText("Revoked", { exact: true })).toHaveCount(0);
  await page
    .getByRole("button", { name: "Consent history", exact: true })
    .click();
  await expect(
    page.getByText("Revoked", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("clinician@example.com", { exact: true }),
  ).toBeVisible();
});

test("audit dates and actor filters remain applied on subsequent pages", async ({
  page,
}) => {
  await base(page);
  const requests: URL[] = [];
  await page.route("**/api/v1/audit-events?**", (route) => {
    const url = new URL(route.request().url());
    requests.push(url);
    return json(route, {
      items: [
        {
          id: url.searchParams.has("cursor") ? "second" : "first",
          occurredAt: "2026-10-09T10:20:30Z",
          actorName: "patient@example.com",
          actorRole: "PATIENT",
          isSelf: true,
          providerName: null,
          entryType: null,
          action: "ENTRY_VIEWED",
        },
      ],
      nextCursor: url.searchParams.has("cursor") ? null : "next-page",
    });
  });
  await page.goto("/en/audit");
  await page.getByText("Filter access history", { exact: true }).click();
  await expect(page.getByText("You", { exact: true })).toBeVisible();
  await expect(page.locator("time")).toHaveAttribute(
    "datetime",
    "2026-10-09T10:20:30Z",
  );
  await page.getByLabel("Action", { exact: true }).selectOption("ENTRY_VIEWED");
  await page.getByLabel("Actor role", { exact: true }).selectOption("PATIENT");
  await page.getByLabel("From date", { exact: true }).fill("2026-10-09");
  await page.getByLabel("Through date", { exact: true }).fill("2026-10-09");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect
    .poll(() => requests.at(-1)?.searchParams.get("until"))
    .toBe("2026-10-10T00:00:00.000Z");
  await page.getByRole("button", { name: "Load more", exact: true }).click();
  await expect
    .poll(() => requests.at(-1)?.searchParams.get("cursor"))
    .toBe("next-page");
  expect(requests.at(-1)?.searchParams.get("actorRole")).toBe("PATIENT");
  expect(requests.at(-1)?.searchParams.get("action")).toBe("ENTRY_VIEWED");
});

test("timeline search queries dates and Provider across pages and resets cleanly", async ({
  page,
}) => {
  await base(page);
  const requests: URL[] = [];
  await page.route("**/api/v1/patients/*/entries?**", (route) => {
    const url = new URL(route.request().url());
    requests.push(url);
    return json(route, {
      items: [
        {
          id: url.searchParams.has("cursor") ? "entry-second" : "entry",
          patientId: PID,
          entryType: "LAB_REPORT",
          occurredAt: "2025-10-01T10:00:00Z",
          recordedAt: "2025-10-01T10:00:00Z",
          isCritical: false,
          supersededById: null,
          sourceProviderId: "provider",
          providerName: "Synthetic Clinic",
          summary: "Hemoglobin",
        },
      ],
      nextCursor: url.searchParams.has("cursor") ? null : "search-next",
    });
  });
  await page.goto("/en/timeline");
  await expect(
    page
      .getByRole("link")
      .filter({ hasText: "Hemoglobin" })
      .getByText("Synthetic Clinic", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Search Medical Entries").fill("Hemoglobin");
  await page
    .getByText("More filters: dates and Provider", { exact: true })
    .click();
  await page.getByLabel("From date", { exact: true }).fill("2025-01-01");
  await page.getByLabel("Provider", { exact: true }).selectOption("provider");
  await page.getByRole("button", { name: "Search history" }).click();
  await expect
    .poll(() => requests.at(-1)?.searchParams.get("q"))
    .toBe("Hemoglobin");
  expect(requests.at(-1)?.searchParams.get("providerId")).toBe("provider");
  expect(requests.at(-1)?.searchParams.get("fromDate")).toBe("2025-01-01");
  await page.getByRole("button", { name: "Load more", exact: true }).click();
  await expect
    .poll(() => requests.at(-1)?.searchParams.get("cursor"))
    .toBe("search-next");
  expect(requests.at(-1)?.searchParams.get("q")).toBe("Hemoglobin");
  expect(requests.at(-1)?.searchParams.get("providerId")).toBe("provider");
  await page.getByRole("button", { name: "Reset filters" }).click();
  await expect.poll(() => requests.at(-1)?.searchParams.has("q")).toBe(false);
});

for (const locale of ["en", "hi", "ta", "ml"]) {
  test(`patient task screens fit mobile and render new copy in ${locale}`, async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await base(page);
    await page.setViewportSize({ width: 390, height: 844 });
    const messageErrors: string[] = [];
    page.on("pageerror", (error) => messageErrors.push(error.message));
    for (const route of ["timeline", "audit", "consent", "consent/new"]) {
      await page.goto(`/${locale}/${route}`);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.locator("nav.fixed")).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      const dimensions = await page.evaluate(() => ({
        width: window.innerWidth,
        content: document.documentElement.scrollWidth,
      }));
      if (dimensions.content > dimensions.width) {
        console.log(
          `${locale}/${route}`,
          await page.evaluate(() =>
            [...document.querySelectorAll("main *")]
              .filter((e) => e.getBoundingClientRect().right > innerWidth)
              .map((e) => ({
                tag: e.tagName,
                classes: e.className,
                text: e.textContent?.slice(0, 60),
                width: e.getBoundingClientRect().width,
              })),
          ),
        );
      }
      expect(dimensions.content, `${locale}/${route}`).toBeLessThanOrEqual(
        dimensions.width,
      );
    }
    expect(
      messageErrors.filter((message) => message.includes("MISSING_MESSAGE")),
    ).toEqual([]);
  });
}

test("the signed-out mobile header fits every locale", async ({ page }) => {
  test.setTimeout(90_000);
  await base(page);
  await page.route("**/api/v1/auth/me", (route) =>
    json(route, { error: { code: "SESSION_EXPIRED" } }, 401),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  for (const locale of ["en", "hi", "ta", "ml"]) {
    await page.goto(`/${locale}/register`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.locator("header a[href$='/login']")).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    const width = await page.evaluate(() => ({
      screen: innerWidth,
      content: document.documentElement.scrollWidth,
    }));
    expect(width.content, locale).toBeLessThanOrEqual(width.screen);
  }
});

test.describe("consent review west of UTC", () => {
  test.use({ timezoneId: "America/Los_Angeles" });
  test("the reviewed record date window retains the selected calendar dates", async ({
    page,
  }) => {
    await base(page);
    await page.goto("/en/consent/new");
    await grantDetails(page);
    await page
      .getByRole("radio", { name: "All entry types", exact: true })
      .check();
    await page.getByLabel("From date (optional)").fill("2026-01-01");
    await page.getByLabel("To date (optional)").fill("2026-10-09");
    await page
      .getByRole("button", { name: "Review access", exact: true })
      .click();
    await expect(
      page.getByText("1 Jan 2026 – 9 Oct 2026", { exact: true }),
    ).toBeVisible();
  });
});
