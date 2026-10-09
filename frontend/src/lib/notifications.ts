import type { NotificationType } from "./generated/api";
export { NotificationTypeValues as NOTIFICATION_TYPES, NotificationChannelValues as NOTIFICATION_CHANNELS } from "./generated/api";
export type { NotificationType, NotificationChannel, Notification, NotificationPreference } from "./generated/api";

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
