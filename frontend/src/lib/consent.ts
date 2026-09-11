// Consent wire types (issue #46 consent screens).
//
// Hand-mirrored from `backend/app/modules/consent/schemas.py` — same
// precedent as `lib/records.ts`: the repo has no OpenAPI-to-TypeScript
// generation set up yet. Keep in sync with `Consent` / `ConsentCreate` /
// `RevocationRequest` until a generator lands.
//
// Scope is entry-type + date window only — never per-entry ticking
// (.claude/rules/frontend.md, docs/domain-model.md).

import type { EntryType } from "./records";

export const CONSENT_PURPOSES = ["TREATMENT", "SECOND_OPINION", "OTHER"] as const;
export type ConsentPurpose = (typeof CONSENT_PURPOSES)[number];

export const CONSENT_STATUSES = ["ACTIVE", "REVOKED", "EXPIRED"] as const;
export type ConsentStatus = (typeof CONSENT_STATUSES)[number];

export interface Consent {
  id: string;
  patientId: string;
  granteeUserId: string;
  granteeName: string | null;
  entryTypes: EntryType[] | null;
  fromDate: string | null;
  toDate: string | null;
  purpose: ConsentPurpose;
  purposeText: string | null;
  status: ConsentStatus;
  expiresAt: string;
  grantedAt: string;
  revokedAt: string | null;
  revocationReason: string | null;
}

export interface ConsentCreate {
  granteeUserId: string;
  entryTypes?: EntryType[] | null;
  fromDate?: string | null;
  toDate?: string | null;
  purpose: ConsentPurpose;
  purposeText?: string | null;
  expiresAt: string;
}

export interface RevocationRequest {
  reason?: string | null;
}
