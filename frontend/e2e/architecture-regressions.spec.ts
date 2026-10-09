import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

const PATIENT_ID = "22222222-2222-2222-2222-222222222222";
const ENTRY_ID = "33333333-3333-3333-3333-333333333333";
const me = { userId: "staff", role: "PROVIDER_STAFF", email: "staff@example.com", emailVerified: true };
const entry = {
  id: ENTRY_ID, patientId: PATIENT_ID, entryType: "CLINICAL_NOTE", occurredAt: "2026-08-01T10:00:00Z",
  recordedAt: "2026-08-01T10:01:00Z", isCritical: false, supersededById: null, sourceProviderId: "provider",
  summary: "Synthetic original", text: "Synthetic original", documents: [], supersedesId: null, metadata: {},
};

async function qa(page: import("@playwright/test").Page, name: string) {
  if (process.env.PULSE_QA_DIR) await page.screenshot({ path: resolve(process.env.PULSE_QA_DIR, `${name}.png`), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
}

test("a patient cannot open the provider entry form", async ({ page }) => {
  await page.route("**/api/v1/auth/me", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...me, role: "PATIENT" }) }));
  await page.goto("/en/timeline/new");
  await expect(page.getByText("Only verified Provider Staff can file or correct entries.")).toBeVisible();
  await expect(page.locator("form")).toHaveCount(0);
});

test("a provider correction preserves patient identity and files a replacement", async ({ page }) => {
  let filed: { path: string; text: string } | undefined;
  await page.route("**/api/v1/**", route => {
    const url = new URL(route.request().url());
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname.endsWith("/auth/me")) return json(me);
    if (url.pathname.endsWith(`/entries/${ENTRY_ID}`)) return json(entry);
    if (route.request().method() === "POST") {
      filed = { path: url.pathname, text: route.request().postDataJSON().text };
      return json({ id: "replacement" }, 201);
    }
    return json({ error: { code: "NOT_FOUND" } }, 404);
  });
  await page.goto(`/en/timeline/new?patientId=${PATIENT_ID}&corrects=${ENTRY_ID}`);
  await expect(page.getByRole("heading", { name: "Correct an entry", exact: true })).toBeVisible();
  await expect(page.getByLabel("Patient ID")).toHaveAttribute("readonly");
  await expect(page.getByLabel("Note text")).toHaveValue("Synthetic original");
  await qa(page, "correction-desktop");
  await page.setViewportSize({ width: 390, height: 844 });
  await qa(page, "correction-mobile");
  await page.getByLabel("Note text").fill("Synthetic correction");
  await page.getByRole("button", { name: "File correction", exact: true }).click();
  await expect(page.getByText("Correction filed", { exact: true })).toBeVisible();
  expect(filed).toEqual({ path: `/api/v1/patients/${PATIENT_ID}/entries/${ENTRY_ID}/corrections`, text: "Synthetic correction" });
});

test("patient ID copy writes the displayed ID to the clipboard", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.route("**/api/v1/patients/me", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({
    id: PATIENT_ID, fullName: "Synthetic Patient", dateOfBirth: null, phone: null, sex: null,
    addressLine: null, city: null, state: null, localePreference: "en", claimed: true,
  }) }));
  await page.goto("/en/profile");
  await page.getByRole("button", { name: "Copy patient ID" }).click();
  await expect(page.getByText("Patient ID copied", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(PATIENT_ID);
  await page.setViewportSize({ width: 390, height: 844 });
  await qa(page, "profile-mobile");
});

test("notifications render the chosen locale and the digest count", async ({ page }) => {
  await page.route("**/api/v1/notifications?*", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({
    items: [{ id: "notification", type: "DAILY_DIGEST", title: "LEGACY_ENGLISH", body: "LEGACY_ENGLISH", params: { viewCount: 3 }, readAt: null, createdAt: "2026-08-01T10:00:00Z" }], nextCursor: null,
  }) }));
  await page.goto("/hi/notifications");
  await expect(page.getByText("पिछली जाँच के बाद आपके रिकॉर्ड 3 बार देखे गए।")).toBeVisible();
  await expect(page.getByText("LEGACY_ENGLISH")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await qa(page, "notifications-mobile");
});

test("preferences expose only working optional delivery channels", async ({ page }) => {
  await page.route("**/api/v1/notification-preferences", route => route.fulfill({ contentType: "application/json", body: JSON.stringify([
    { notificationType: "RECORD_UPLOADED", channel: "EMAIL", enabled: true },
    { notificationType: "RECORD_UPLOADED", channel: "SMS", enabled: true },
    { notificationType: "RECORD_UPLOADED", channel: "IN_APP", enabled: true },
  ]) }));
  await page.goto("/en/notifications/preferences");
  await expect(page.getByRole("switch", { name: "In-app" })).toBeVisible();
  await expect(page.getByRole("switch")).toHaveCount(1);
});
