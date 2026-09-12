"""Roles, Permissions, and the pure Role -> Permission resolution.

`ROLE_PERMISSIONS` is the whole authorization model for Phase 1: a static
table, resolved without a database or a request. No entry grants a read of
clinical data, so no Administrator can hold one (ADR-0007).
"""

from enum import StrEnum


class Role(StrEnum):
    PATIENT = "PATIENT"
    CLINICIAN = "CLINICIAN"
    PROVIDER_STAFF = "PROVIDER_STAFF"
    ADMINISTRATOR = "ADMINISTRATOR"


class Permission(StrEnum):
    # A signed-in Patient reading their own Patient profile.
    PATIENT_PROFILE_READ_SELF = "PATIENT_PROFILE_READ_SELF"
    # Changing one's own credentials (password / email). Step-up guarded.
    USER_CREDENTIALS_CHANGE = "USER_CREDENTIALS_CHANGE"
    # Reading Medical Entries. The route guard is coarse (a Role holds it or
    # not); which entries the actor actually sees is decided per-request by
    # `accessible_entries` (Phase 3). No Administrator holds it (ADR-0007).
    RECORDS_READ = "RECORDS_READ"
    # Filing Medical Entries / uploading Documents — Provider Staff only.
    RECORDS_WRITE = "RECORDS_WRITE"
    # A Patient managing and reviewing Consent over their own record.
    CONSENT_READ_SELF = "CONSENT_READ_SELF"
    CONSENT_MANAGE_SELF = "CONSENT_MANAGE_SELF"
    # A Patient reading their own audit trail (filtered projection).
    AUDIT_READ_SELF = "AUDIT_READ_SELF"
    # A Patient reading their own notification digest.
    NOTIFICATION_READ_SELF = "NOTIFICATION_READ_SELF"
    # A Patient reading their own notification preferences.
    NOTIFICATION_PREFERENCES_READ_SELF = "NOTIFICATION_PREFERENCES_READ_SELF"
    # A Patient marking their own notifications read and changing their own
    # per-type/per-channel preferences. Mandatory types are never settable
    # through this — the service rejects it regardless of permission.
    NOTIFICATION_MANAGE_SELF = "NOTIFICATION_MANAGE_SELF"
    # Reading a Provider organisation's public identity (name, kind, city).
    # No clinical data — every signed-in role may hold it.
    PROVIDER_READ = "PROVIDER_READ"
    # A Clinician requesting emergency access without Consent. Clinician
    # only (#44) — a Provider Staff member already has Provider-scoped
    # access, and no other role may bypass Consent this way.
    BREAK_GLASS_REQUEST = "BREAK_GLASS_REQUEST"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.PATIENT: frozenset(
        {
            Permission.PATIENT_PROFILE_READ_SELF,
            Permission.USER_CREDENTIALS_CHANGE,
            Permission.RECORDS_READ,
            Permission.CONSENT_READ_SELF,
            Permission.CONSENT_MANAGE_SELF,
            Permission.AUDIT_READ_SELF,
            Permission.NOTIFICATION_READ_SELF,
            Permission.NOTIFICATION_PREFERENCES_READ_SELF,
            Permission.NOTIFICATION_MANAGE_SELF,
            Permission.PROVIDER_READ,
        }
    ),
    Role.CLINICIAN: frozenset(
        {
            Permission.USER_CREDENTIALS_CHANGE,
            Permission.RECORDS_READ,
            Permission.PROVIDER_READ,
            Permission.BREAK_GLASS_REQUEST,
        }
    ),
    Role.PROVIDER_STAFF: frozenset(
        {
            Permission.USER_CREDENTIALS_CHANGE,
            Permission.RECORDS_READ,
            Permission.RECORDS_WRITE,
            Permission.PROVIDER_READ,
        }
    ),
    Role.ADMINISTRATOR: frozenset(
        {Permission.USER_CREDENTIALS_CHANGE, Permission.PROVIDER_READ}
    ),
}


def resolve_permissions(role: Role) -> frozenset[Permission]:
    """Every Permission a Role holds. Total over Role; never raises."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def role_has_permission(role: Role, permission: Permission) -> bool:
    return permission in resolve_permissions(role)
