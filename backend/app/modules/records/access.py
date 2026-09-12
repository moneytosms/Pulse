"""Actor -> patient access resolution (#40, P3.4).

`repository.accessible_entries` turns access rules into a SQL filter over
`MedicalEntry`; that filter is silent about *whether an actor has a
relationship to a patient at all* — it just returns fewer or no rows. The
service layer needs the other question answered directly: "should this
404 right now?", independent of whether the patient's history happens to
be empty (an empty timeline is not the same thing as no relationship, and
must not 404).

`resolve_patient_access` is that lookup: role plus whatever live grant
material backs each rule, in one place, so the service's identity gate
and `accessible_entries`'s SQL filter never drift out of sync.

Administrator resolves to no access, on every field — there is no branch
below that sets one for that role. That absence is what makes both this
function and `accessible_entries` deny an Administrator "naturally"
(ADR-0007): nothing here or in the repository special-cases the role.

Rules 3–4 (Clinician consent, break-glass — #41, P3.5) resolve here too:
the LIVE `access_permission` rows a Clinician holds for the patient
(`repository.live_permissions_for`), matched against a specific Entry's
type/date only inside `accessible_entries`'s SQL, not here; and whether
an active break-glass grant exists (`repository.active_break_glass_for`),
unscoped — break-glass is emergency access without Consent
(domain-model.md), so it carries no entry-type or date material to
resolve.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.authz import Role
from app.modules.records import repository


@dataclass(frozen=True)
class PatientAccess:
    """What `actor` may see of one patient's clinical record.

    `owns_own_history` — rule 1: `actor` is that Patient.
    `provider_id` — rule 2: the Provider whose authored entries `actor`
        (Provider Staff) may see; None if `actor` is not staff, or staff
        at no Provider.
    `permissions` — rule-3 material: `actor`'s live `AccessPermission`
        rows for this patient. Matching these against a specific Entry's
        type/date happens only in `repository.accessible_entries`'s SQL,
        not here.
    `break_glass_active` — rule 4: whether `actor` (a Clinician) holds an
        unexpired break-glass grant for this patient. Unscoped — see
        module docstring.
    """

    owns_own_history: bool
    provider_id: UUID | None
    permissions: tuple[repository.LivePermission, ...]
    break_glass_active: bool

    @property
    def has_any_access(self) -> bool:
        """True iff some rule could grant `actor` a view of this
        patient's record — the identity gate `_authorize_entry_access`
        uses to decide 404 vs proceed. Never true for an Administrator:
        no branch in `resolve_patient_access` ever sets a field for that
        role (ADR-0007)."""
        return (
            self.owns_own_history
            or self.provider_id is not None
            or bool(self.permissions)
            or self.break_glass_active
        )


async def resolve_patient_access(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> PatientAccess:
    """Resolve `actor`'s relationship to `patient_id`. No SQL against
    `medical_entry` here — this is the identity/consent gate, not the
    entry filter (`repository.accessible_entries` is built from exactly
    these same rule-1/rule-2 lookups)."""
    owns_own_history = await repository.actor_owns_patient(session, actor, patient_id)
    provider_id = await repository.provider_id_for_staff_actor(session, actor)

    permissions: tuple[repository.LivePermission, ...] = ()
    break_glass_active = False
    if actor.role is Role.CLINICIAN:
        permissions = tuple(
            await repository.live_permissions_for(
                session, patient_id=patient_id, grantee_user_id=actor.user_id
            )
        )
        break_glass_active = await repository.active_break_glass_for(
            session, patient_id=patient_id, clinician_user_id=actor.user_id
        )

    # Role.ADMINISTRATOR: no branch. ADR-0007 — never any clinical access;
    # that absence, not a special case, is what denies the role.

    return PatientAccess(
        owns_own_history=owns_own_history,
        provider_id=provider_id,
        permissions=permissions,
        break_glass_active=break_glass_active,
    )
