import { expect, test } from "@playwright/test";

// Every backend call is mocked here — no FastAPI / Postgres / Redis needed
// (pattern: e2e/timeline.spec.ts). Covers issue #34: field-level validation
// from the error envelope's `details` array, and explicit 413 handling.

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", route => route.fulfill({
    contentType: "application/json", body: JSON.stringify({
      userId: "u-staff", email: "staff@example.com", role: "PROVIDER_STAFF", emailVerified: true,
    }),
  }));
});

const PATIENT_ID = "22222222-2222-2222-2222-222222222222";

async function fillCommonFields(page: import("@playwright/test").Page) {
  // Filling before hydration lets React reset the controlled inputs.
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Patient ID").fill(PATIENT_ID);
  await page.getByRole("combobox", { name: "Entry type" }).click();
  await page.getByRole("option", { name: "Diagnosis" }).click();
  await page.locator('input[type="datetime-local"]').fill("2026-08-01T10:00");
  await page.getByLabel("Code system").fill("ICD-10");
  await page.getByLabel("Code", { exact: true }).fill("E11");
}

test("a stubbed 422 highlights the right field from the details array", async ({ page }) => {
  await page.route("**/api/v1/patients/**/entries", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "VALIDATION_ERROR",
          message: "Validation failed.",
          details: [{ field: "body.displayName", code: "missing" }],
        },
      }),
    });
  });

  await page.goto("/en/timeline/new");
  await fillCommonFields(page);
  await page.getByRole("button", { name: "File entry" }).click();

  const displayNameField = page.getByLabel("Display name");
  await expect(displayNameField).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByText("This field is required.")).toBeVisible();

  // Only the field named in `details` is flagged.
  await expect(page.getByLabel("Code system")).not.toHaveAttribute("aria-invalid", "true");
});

test("a stubbed 413 on document upload shows the size-specific message", async ({ page }) => {
  await page.route("**/api/v1/patients/**/entries", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "new-entry-1" }),
    });
  });
  await page.route("**/api/v1/patients/**/entries/**/documents", async (route) => {
    await route.fulfill({
      status: 413,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "PAYLOAD_TOO_LARGE",
          message: "The file exceeds the upload size limit.",
          details: [],
        },
      }),
    });
  });

  await page.goto("/en/timeline/new");
  await fillCommonFields(page);
  await page
    .locator('input[type="file"]')
    .setInputFiles({ name: "report.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4") });
  await page.getByRole("button", { name: "File entry" }).click();

  await expect(
    page.getByText("This file is too large — compress or split it and try again."),
  ).toBeVisible();
});

test("a dropped document is selected and can be removed", async ({ page }) => {
  await page.goto("/en/timeline/new");
  await page.waitForLoadState("networkidle");

  await page.locator('[data-testid="document-dropzone"]').evaluate((dropzone) => {
    const files = new DataTransfer();
    files.items.add(new File(["%PDF-1.4"], "blood-report.pdf", { type: "application/pdf" }));
    dropzone.dispatchEvent(
      new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: files }),
    );
  });

  await expect(page.getByText("blood-report.pdf")).toBeVisible();
  await expect(page.getByText("8 B")).toBeVisible();
  await page.getByRole("button", { name: "Remove file" }).click();
  await expect(page.getByText("Drag and drop a document here")).toBeVisible();
});

test("the dropzone rejects unsupported documents and opens the file picker", async ({ page }) => {
  await page.goto("/en/timeline/new");
  await page.waitForLoadState("networkidle");

  await page.locator('[data-testid="document-dropzone"]').evaluate((dropzone) => {
    const files = new DataTransfer();
    files.items.add(new File(["notes"], "notes.txt", { type: "text/plain" }));
    dropzone.dispatchEvent(
      new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: files }),
    );
  });

  await expect(page.getByText("Choose a PDF, PNG or JPEG file.", { exact: true })).toBeVisible();
  const fileChooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Browse files" }).click();
  const fileChooser = await fileChooserPromise;
  await fileChooser.setFiles({
    name: "scan.png",
    mimeType: "image/png",
    buffer: Buffer.from("png"),
  });
  await expect(page.getByText("scan.png")).toBeVisible();
});

test("Provider Staff files from the patient record with the id prefilled", async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname.endsWith("/auth/me")) {
      return json(200, { userId: "u-staff", email: "staff@example.com", role: "PROVIDER_STAFF", emailVerified: true });
    }
    if (url.pathname === `/api/v1/patients/${PATIENT_ID}/entries`) {
      return json(200, { items: [], nextCursor: null });
    }
    return json(404, { error: { code: "NOT_FOUND", message: "not found" } });
  });

  await page.goto(`/en/patients/${PATIENT_ID}/records`);
  await page.getByRole("link", { name: "File new entry" }).click();
  await expect(page).toHaveURL(new RegExp(`/en/timeline/new\\?patientId=${PATIENT_ID}`));
  await expect(page.getByLabel("Patient ID")).toHaveValue(PATIENT_ID);
});
