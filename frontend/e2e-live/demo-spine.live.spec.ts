import { expect, test, type Page } from "@playwright/test";

// Live demo spine (issue #56, plan 006). Runs against the real Compose
// stack — Caddy, frontend, backend, Postgres, Redis — with nothing mocked.
// Requires `docker compose up --build -d --wait` from the repo root first.
// Three browser contexts (staff, patient, clinician) so cookies don't
// collide, mirroring three separate people in the demo.

const PATIENT_ID = "0c96112a-1653-5403-999c-30ec1ef6dda8";

const STAFF_EMAIL = "staff000@example.com";
const PATIENT_EMAIL = "demo.patient.en@example.com";
const CLINICIAN_EMAIL = "clinician0@example.com";
const PASSWORD = "Pulse@demo1";

async function login(page: Page, email: string) {
  await page.goto("/en/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("full demo spine against the live stack: file, grant, read, audit, revoke, lockout", async ({
  browser,
}) => {
  test.slow();

  const displayName = `Live check ${Date.now()}`;

  const staffContext = await browser.newContext();
  const patientContext = await browser.newContext();
  const clinicianContext = await browser.newContext();

  try {
    const staffPage = await staffContext.newPage();
    const patientPage = await patientContext.newPage();
    const clinicianPage = await clinicianContext.newPage();

    // 1. Staff files an entry
    await login(staffPage, STAFF_EMAIL);
    await staffPage.goto(`/en/patients/${PATIENT_ID}/records`);
    await staffPage.waitForLoadState("networkidle");
    await staffPage.getByRole("link", { name: "File new entry" }).click();
    await staffPage.waitForLoadState("networkidle");
    await expect(staffPage.getByLabel("Patient ID")).toHaveValue(PATIENT_ID);
    await staffPage.getByRole("combobox", { name: "Entry type" }).click();
    await staffPage.getByRole("option", { name: "Diagnosis" }).click();
    await staffPage
      .locator('input[type="datetime-local"]')
      .fill("2026-08-01T10:00");
    await staffPage.getByLabel("Code system").fill("ICD-10");
    await staffPage.getByLabel("Code", { exact: true }).fill("E11");
    await staffPage.getByLabel("Display name").fill(displayName);
    await staffPage.getByRole("button", { name: "File entry" }).click();
    await expect(staffPage.getByText("View entry")).toBeVisible();
    await staffPage.getByText("View entry").click();
    await expect(staffPage.getByText(displayName)).toBeVisible();

    // 2. Patient grants consent to the clinician
    await login(patientPage, PATIENT_EMAIL);
    await patientPage.goto("/en/consent/new");
    await patientPage.waitForLoadState("networkidle");
    await patientPage.getByLabel("Clinician email").fill(CLINICIAN_EMAIL);
    await patientPage.getByRole("combobox", { name: "Purpose" }).click();
    await patientPage.getByRole("option", { name: "Treatment" }).click();
    const expiry = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
    const expiryValue = expiry.toISOString().slice(0, 16);
    await patientPage.locator('input[type="datetime-local"]').fill(expiryValue);
    await patientPage
      .getByRole("radio", { name: "All entry types", exact: true })
      .check();
    await patientPage
      .getByRole("button", { name: "Review access", exact: true })
      .click();
    await expect(
      patientPage.getByRole("heading", { name: "Review before sharing" }),
    ).toBeVisible();
    await patientPage.getByLabel("Confirm with your password").fill(PASSWORD);
    await patientPage.getByRole("button", { name: "Grant access" }).click();
    await expect(patientPage.getByText("Access granted")).toBeVisible();

    // 3. Clinician finds the patient through the consented-patients list
    //    (plan 004) instead of pasting the id, and reads the record.
    await login(clinicianPage, CLINICIAN_EMAIL);
    await clinicianPage.goto("/en/clinician");
    await clinicianPage.waitForLoadState("networkidle");
    await expect(
      clinicianPage.getByText("Patients who have given you access"),
    ).toBeVisible();
    // The row's accessible name carries the patient's identity — the id is
    // part of it, so this finds the right link without hardcoding the name.
    // .first() keeps reruns safe if a crashed earlier run left a grant.
    await clinicianPage.getByRole("link", { name: PATIENT_ID }).first().click();
    await clinicianPage.waitForLoadState("networkidle");
    await expect(
      clinicianPage.getByRole("heading", { name: "Patient record" }),
    ).toBeVisible();
    await expect(clinicianPage.getByText(displayName)).toBeVisible();

    // 4. Patient's own audit view shows at least one row
    await patientPage.goto("/en/audit");
    await patientPage.waitForLoadState("networkidle");
    await expect(patientPage.locator("table tbody tr").first()).toBeVisible();

    // 5. Revoke every ACTIVE consent to this clinician —
    //    CI sees exactly one, but a long-lived demo volume can carry stale
    //    grants from earlier rehearsals, and any survivor defeats step 6.
    await patientPage.goto("/en/consent");
    await patientPage.waitForLoadState("networkidle");
    for (let i = 0; i < 3; i++) {
      const row = patientPage
        .locator("li", { hasText: CLINICIAN_EMAIL })
        .filter({ has: patientPage.getByRole("button", { name: "Revoke" }) });
      if ((await row.count()) === 0) break;
      await row.first().getByRole("button", { name: "Revoke" }).click();
      await row.first().getByRole("button", { name: "Confirm revoke" }).click();
      await expect(
        patientPage.getByText(
          "Consent revoked. Check remaining current access below.",
        ),
      ).toBeVisible();
    }

    // 6. Clinician is now locked out
    await clinicianPage.reload();
    await clinicianPage.waitForLoadState("networkidle");
    await expect(clinicianPage.getByText("Record not found")).toBeVisible();
    await expect(clinicianPage.getByText(displayName)).not.toBeVisible();
  } finally {
    await staffContext.close();
    await patientContext.close();
    await clinicianContext.close();
  }
});
