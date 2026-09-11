// Audit wire type (issue #46 "who accessed my records" view).
//
// Hand-mirrored from `backend/app/modules/audit/schemas.py` — same
// precedent as `lib/records.ts`: no OpenAPI-to-TypeScript generation set up
// yet. This is the Patient's filtered projection only — never an identifier,
// never clinical content (.claude/rules/clinical-safety.md).

export interface AuditEventProjection {
  id: string;
  occurredAt: string;
  actorName: string;
  actorRole: string;
  providerName: string | null;
  action: string;
  entryType: string | null;
}
