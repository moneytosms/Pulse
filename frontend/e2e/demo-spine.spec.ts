import { expect, test } from "@playwright/test";

// Full demo journey (issue #56): signup -> upload -> timeline -> grant
// consent -> clinician read -> patient audit view -> revoke -> clinician
// locked out. Every backend call is mocked here, same pattern as the rest of
// e2e/ (smoke.spec.ts, timeline.spec.ts) — the suite is deliberately
// self-contained and needs no FastAPI, Postgres, or Redis. Consent state is
// held in a closure variable so the revoke step actually changes what the
// clinician-read step sees later in the same test, mirroring what the real
// `accessible_entries` filter would do.

const PATIENT_ID = "33333333-3333-3333-3333-333333333333";
const CLINICIAN_USER_ID = "44444444-4444-4444-4444-444444444444";
const CONSENT_ID = "55555555-5555-5555-5555-555555555555";
const ENTRY_ID = "new-entry-1";

const PATIENT_PROFILE = {
  id: PATIENT_ID,
  fullName: "Priya Nair",
  dateOfBirth: "1985-02-20",
  sex: "Female",
  phone: "9876500000",
  addressLine: "4 Lake Road",
  city: "Kochi",
  state: "Kerala",
  localePreference: "en",
  claimed: true,
};

const FILED_ENTRY_SUMMARY = {
  id: ENTRY_ID,
  patientId: PATIENT_ID,
  entryType: "DIAGNOSIS",
  occurredAt: "2026-08-01T10:00:00Z",
  recordedAt: "2026-08-01T10:05:00Z",
  isCritical: false,
  supersededById: null,
  sourceProviderId: null,
  summary: "Type 2 diabetes mellitus",
};

function consentFixture(
  status: "ACTIVE" | "REVOKED",
  revokedAt: string | null = null,
) {
  return {
    id: CONSENT_ID,
    patientId: PATIENT_ID,
    granteeUserId: CLINICIAN_USER_ID,
    granteeName: "Dr. Fathima Rasheed",
    entryTypes: null,
    fromDate: null,
    toDate: null,
    purpose: "TREATMENT",
    purposeText: null,
    status,
    expiresAt: "2027-01-01T00:00:00Z",
    grantedAt: "2026-08-02T00:00:00Z",
    revokedAt,
    revocationReason: revokedAt ? "No longer needed" : null,
  };
}

test("full demo spine: signup, upload, grant, clinician read, audit, revoke, lockout", async ({
  page,
}) => {
  test.slow(); // Eight navigation and form steps against the development server.
  let consentStatus: "NONE" | "ACTIVE" | "REVOKED" = "NONE";
  // The mock can't tell "patient viewing their own timeline" apart from
  // "clinician viewing the same patient's record" by URL alone — both hit
  // `/patients/{id}/entries`. The real backend distinguishes them by actor
  // inside `accessible_entries` (owner access vs. consent-gated access); this
  // flag stands in for "which actor is making the request right now" and is
  // flipped by the test immediately before each clinician-perspective step.
  let asClinician = false;
  // Mirrors the backend's `requires_step_up()` on POST /consents: a grant
  // without a recent password re-entry is refused.
  let steppedUp = false;

  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const json = (status: number, body: unknown) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    if (url.pathname.endsWith("/auth/me"))
      return json(200, {
        userId: "u-staff",
        role: "PROVIDER_STAFF",
        email: "staff@example.com",
        emailVerified: true,
      });

    // --- Signup ---
    if (url.pathname.endsWith("/auth/register") && req.method() === "POST") {
      return json(201, { userId: "u-priya" });
    }

    // --- Identity ---
    if (url.pathname.endsWith("/patients/me"))
      return json(200, PATIENT_PROFILE);

    // --- Upload (P2 entry filing) ---
    if (
      url.pathname === `/api/v1/patients/${PATIENT_ID}/entries` &&
      req.method() === "POST"
    ) {
      return json(201, { id: ENTRY_ID });
    }
    if (
      url.pathname === `/api/v1/patients/${PATIENT_ID}/entries` &&
      req.method() === "GET"
    ) {
      // Clinician read is consent-gated (accessible_entries); the patient's
      // own timeline read is not.
      if (asClinician && consentStatus !== "ACTIVE") {
        return json(404, {
          error: { code: "NOT_FOUND", message: "not found" },
        });
      }
      return json(200, { items: [FILED_ENTRY_SUMMARY], nextCursor: null });
    }

    // --- Consent grant/list/revoke ---
    if (url.pathname === "/api/v1/clinicians/lookup") {
      return url.searchParams.get("email") === "fathima@example.com"
        ? json(200, { userId: CLINICIAN_USER_ID, email: "fathima@example.com" })
        : json(404, { error: { code: "NOT_FOUND", message: "not found" } });
    }
    if (url.pathname === "/api/v1/auth/step-up" && req.method() === "POST") {
      const { password } = req.postDataJSON() as { password: string };
      if (password !== "correct horse battery staple") {
        return json(401, {
          error: { code: "INVALID_CREDENTIALS", message: "bad password" },
        });
      }
      steppedUp = true;
      return json(200, {});
    }
    if (
      url.pathname === "/api/v1/consents" &&
      req.method() === "POST" &&
      !steppedUp
    ) {
      return json(403, {
        error: { code: "STEP_UP_REQUIRED", message: "step up" },
      });
    }
    if (url.pathname === "/api/v1/consents" && req.method() === "POST") {
      const body = req.postDataJSON() as { granteeUserId: string };
      if (body.granteeUserId !== CLINICIAN_USER_ID) {
        return json(422, {
          error: { code: "VALIDATION_ERROR", message: "bad grantee" },
        });
      }
    }
    if (url.pathname === "/api/v1/consents" && req.method() === "POST") {
      consentStatus = "ACTIVE";
      return json(201, consentFixture("ACTIVE"));
    }
    if (url.pathname === "/api/v1/consents" && req.method() === "GET") {
      const items =
        consentStatus === "NONE"
          ? []
          : [
              consentFixture(
                consentStatus === "REVOKED" ? "REVOKED" : "ACTIVE",
                consentStatus === "REVOKED" ? "2026-08-03T00:00:00Z" : null,
              ),
            ];
      return json(200, { items, nextCursor: null });
    }
    if (
      url.pathname === `/api/v1/consents/${CONSENT_ID}/revocation` &&
      req.method() === "POST"
    ) {
      consentStatus = "REVOKED";
      return json(200, consentFixture("REVOKED", "2026-08-03T00:00:00Z"));
    }

    // --- Patient audit view ---
    if (url.pathname === "/api/v1/audit-events") {
      const items =
        consentStatus === "NONE"
          ? []
          : [
              {
                id: "audit-1",
                occurredAt: "2026-08-02T12:00:00Z",
                actorName: "Dr. Fathima Rasheed",
                actorRole: "CLINICIAN",
                providerName: "Amrita Hospital",
                action: "ENTRY_VIEWED",
                entryType: "DIAGNOSIS",
              },
            ];
      return json(200, { items, nextCursor: null });
    }

    return json(404, { error: { code: "NOT_FOUND", message: "not found" } });
  });

  // 1. Signup
  await page.goto("/en/register");
  // Filling before hydration lets React reset the controlled inputs.
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email address").fill("priya@example.com");
  await page.getByLabel("Password").fill("correct horse battery staple");
  // Sign-up creates a Patient; there is no role field.
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/en\/verify-pending/);
  await expect(
    page.getByRole("heading", { name: "Confirm your email address" }),
  ).toBeVisible();

  // 2. Upload (file a Diagnosis entry as the newly signed-up patient)
  await page.goto("/en/timeline/new");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Patient ID").fill(PATIENT_ID);
  await page.getByRole("combobox", { name: "Entry type" }).click();
  await page.getByRole("option", { name: "Diagnosis" }).click();
  await page.locator('input[type="datetime-local"]').fill("2026-08-01T10:00");
  await page.getByLabel("Code system").fill("ICD-10");
  await page.getByLabel("Code", { exact: true }).fill("E11");
  await page.getByLabel("Display name").fill("Type 2 diabetes mellitus");
  await page.getByRole("button", { name: "File entry" }).click();
  await expect(page.getByText("View entry")).toBeVisible();

  // 3. Timeline shows the filed entry
  await page.goto("/en/timeline");
  await expect(
    page.getByRole("heading", { name: "Your timeline" }),
  ).toBeVisible();
  await expect(page.getByText("Type 2 diabetes mellitus")).toBeVisible();

  // 4. Grant consent to the clinician
  await page.goto("/en/consent/new");
  await page.getByLabel("Clinician email").fill("nobody@example.com");
  await page.getByRole("combobox", { name: "Purpose" }).click();
  await page.getByRole("option", { name: "Treatment" }).click();
  await page.locator('input[type="datetime-local"]').fill("2027-01-01T00:00");
  await page
    .getByRole("radio", { name: "All entry types", exact: true })
    .check();
  await page
    .getByRole("button", { name: "Review access", exact: true })
    .click();
  await expect(
    page.getByText("No clinician is registered with that email."),
  ).toBeVisible();

  await page.getByLabel("Clinician email").fill("fathima@example.com");
  await page
    .getByRole("button", { name: "Review access", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Review before sharing" }),
  ).toBeVisible();
  await page.getByLabel("Confirm with your password").fill("wrong password");
  await page.getByRole("button", { name: "Grant access" }).click();
  await expect(page.getByText("That password is not correct.")).toBeVisible();

  await page
    .getByLabel("Confirm with your password")
    .fill("correct horse battery staple");
  await page.getByRole("button", { name: "Grant access" }).click();
  await expect(page.getByText("Access granted")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Back to who has access" }),
  ).toBeVisible();

  // 5. Clinician reads the patient's record — consent now active
  asClinician = true;
  await page.goto(`/en/patients/${PATIENT_ID}/records`);
  await expect(
    page.getByRole("heading", { name: "Patient record" }),
  ).toBeVisible();
  await expect(page.getByText("Type 2 diabetes mellitus")).toBeVisible();
  asClinician = false;

  // 6. Patient's own audit view shows the clinician's read
  await page.goto("/en/audit");
  await expect(
    page.getByRole("heading", { name: "Who accessed my records" }),
  ).toBeVisible();
  await expect(page.getByText("Dr. Fathima Rasheed")).toBeVisible();
  await expect(page.getByText("Amrita Hospital")).toBeVisible();

  // 7. Patient revokes consent
  await page.goto("/en/consent");
  await expect(page.getByText("Dr. Fathima Rasheed")).toBeVisible();
  await page.getByRole("button", { name: "Revoke" }).click();
  await page.getByRole("button", { name: "Confirm revoke" }).click();
  await expect(
    page.getByText("Consent revoked. Check remaining current access below."),
  ).toBeVisible();

  // 8. Clinician is now locked out — identical 404 to "patient doesn't exist"
  asClinician = true;
  await page.goto(`/en/patients/${PATIENT_ID}/records`);
  await expect(page.getByText("Record not found")).toBeVisible();
  await expect(page.getByText("We could not find that record.")).toBeVisible();
});
