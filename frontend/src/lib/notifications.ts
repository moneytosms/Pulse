// Notification wire types (issue #46 notification centre + preferences).
//
// Hand-mirrored from `backend/app/modules/notifications/schemas.py` — same
// precedent as `lib/records.ts` / `lib/audit.ts` / `lib/consent.ts`: no
// OpenAPI-to-TypeScript generation set up yet. Keep in sync with
// `Notification` / `NotificationPreference` until a generator lands.

export const NOTIFICATION_TYPES = [
  "CONSENT_GRANTED",
  "CONSENT_REVOKED",
  "RECORD_UPLOADED",
  "BREAK_GLASS_ACCESS",
  "DAILY_DIGEST",
] as const;
export type NotificationType = (typeof NOTIFICATION_TYPES)[number];

export const NOTIFICATION_CHANNELS = ["EMAIL", "SMS", "IN_APP"] as const;
export type NotificationChannel = (typeof NOTIFICATION_CHANNELS)[number];

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  body: string;
  readAt: string | null;
  createdAt: string;
}

export interface NotificationPreference {
  notificationType: NotificationType;
  channel: NotificationChannel;
  enabled: boolean;
}

/**
 * Mandatory types — never subject to a preference check, never shown in the
 * preferences list, absent rather than locked
 * (`backend/app/modules/notifications/service.py` `MANDATORY_TYPES`, issue
 * #43; .claude/rules/clinical-safety.md). A break-glass access and a
 * consent revocation must always reach the Patient; consent-granted,
 * record-uploaded and the daily digest are all opt-outable.
 */
export const MANDATORY_NOTIFICATION_TYPES: ReadonlySet<NotificationType> = new Set([
  "BREAK_GLASS_ACCESS",
  "CONSENT_REVOKED",
]);
