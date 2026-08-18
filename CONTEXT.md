# Pulse

A lifelong electronic health record platform. Patients own their medical history; providers contribute to it; clinicians read it only with the patient's consent, and every access is recorded.

This file is the glossary and nothing else. It defines what terms *mean*, never how they are implemented — implementation lives in `docs/`.

## Language

### People and accounts

**User**:
An authenticated account in the system. Every User holds exactly one Role.
_Avoid_: account, login

**Role**:
What a User is permitted to be: `PATIENT`, `CLINICIAN`, `PROVIDER_STAFF`, or `ADMINISTRATOR`.
_Avoid_: permission level, user type

**Patient**:
A person whose medical history Pulse holds. A Patient may exist without a User — a provider can create one for someone who has never registered. The aggregate root: everything clinical hangs beneath a Patient.
_Avoid_: Patient Record, subject, client

**Unclaimed Patient**:
A Patient with no linked User. Created by a provider, later claimed when that person registers.

**Provider**:
An organisation that delivers care — a hospital, clinic, or lab.
_Avoid_: facility, institution, org

**Provider Staff**:
A User employed by a Provider who uploads and records clinical data on its behalf.
_Avoid_: staff member, uploader

**Clinician**:
A User who reads a Patient's medical history in order to treat them. Distinct from Provider Staff: Provider Staff contribute data, Clinicians consume it.
_Avoid_: doctor, physician, practitioner

### Clinical data

**Medical History**:
The whole collection of a Patient's clinical data. A relationship, not a thing — there is no entity by this name.
_Avoid_: Patient Record, chart, file

**Medical Entry**:
One clinical event in a Patient's medical history. Always exactly one of five kinds: Diagnosis, Prescription, Lab Report, Procedure, or Clinical Note.
_Avoid_: record, event, item

**Medical Document**:
A file attached to a Medical Entry — a scanned prescription, a lab PDF, a medical image. Pulse stores and serves it; Pulse never interprets it.
_Avoid_: attachment, upload, file

**Superseded**:
The state of a Medical Entry that has been corrected. The original is never edited or deleted; a new Entry replaces it and the original is marked superseded.
_Avoid_: amended, updated, revised, deleted

**Critical**:
A flag on a Medical Entry marking it as clinically urgent — something a Clinician must not miss.

### Consent and access

**Consent**:
A Patient's recorded agreement that someone may read some part of their medical history. The legal fact: *the patient agreed*.
_Avoid_: permission, authorisation, approval

**Permission**:
The system's live enforcement of a Consent. The technical fact: *access is currently allowed*. Derived from Consent, never granted independently.
_Avoid_: consent, access right, grant

**Revocation**:
A Patient withdrawing a Consent. Takes effect immediately: the derived Permission stops allowing access at once, including for a Clinician already mid-session.

**Scope**:
The extent of a Consent — which parts of a medical history it covers, and for how long.

### Records integrity

**Audit Event**:
An immutable record that something sensitive happened: who did what, to which resource, when, and whether it succeeded. Append-only. Never modified, never deleted.
_Avoid_: log entry, activity, history

**Duplicate Review Item**:
A pair of Patients the system suspects are the same person, awaiting a human decision.
_Avoid_: match, collision, conflict

**Merge**:
Resolving a Duplicate Review Item by combining two Patients into one. Destructive, always human-initiated, never automatic.

**Data Quality Flag**:
A marker that something about a Patient's data is suspect — missing, implausible, or contradictory.

### Derived data

**Summary Insight**:
Analytics computed *from* Medical Entries — a trend, an average, a count. A concept, not a stored entity: insights are computed on read and never persisted. Never a source of clinical truth, and never the origin of a clinical fact.
_Avoid_: analytics record, metric, report

## Two distinctions that carry the design

**Consent is not Permission.** Consent is what the Patient agreed to; Permission is what the system currently allows. One produces the other, and keeping them separate is what makes revocation and auditing coherent.

**The interface is localized; clinical data is not.** Pulse ships in English, Hindi, Tamil and Malayalam. That applies to labels, messages and navigation only. A Diagnosis recorded as "Type 2 diabetes mellitus" reads that way in every locale — translating clinical content would be inventing medical claims.
