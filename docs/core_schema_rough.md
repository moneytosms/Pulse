================================================================================
PULSE - CONCEPTUAL DOMAIN MODEL (NORMALIZED CORE SCHEMA)
================================================================================

┌──────────────────────────────────────────────────────────────────────────────┐
│ AUTHENTICATION & IDENTITY DOMAIN                                            │
└──────────────────────────────────────────────────────────────────────────────┘

Role
├── Role Name
└── Role Permissions

User
├── Role
├── Email
├── Password Hash
├── Profile Information
├── Account Status
└── Last Login

Relationships:
Role (1) ────────< (N) User



┌──────────────────────────────────────────────────────────────────────────────┐
│ PATIENT DOMAIN                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

Patient
├── User Account
├── Demographics
├── Contact Information
├── Emergency Contacts
└── Patient Record

Patient Record
├── Record Metadata
├── Current Status
├── Medical Entries
├── Consent Records
└── Access Permissions

Relationships:
User (1) ──────── (1) Patient
Patient (1) ──────── (1) Patient Record



┌──────────────────────────────────────────────────────────────────────────────┐
│ PROVIDER DOMAIN                                                             │
└──────────────────────────────────────────────────────────────────────────────┘

Provider
├── Name
├── Provider Type
├── Contact Information
└── Staff Members

Provider Staff
├── User Account
├── Provider
├── Designation
└── Professional Information

Relationships:
Provider (1) ────────< (N) Provider Staff
User (1) ──────── (1) Provider Staff



┌──────────────────────────────────────────────────────────────────────────────┐
│ MEDICAL RECORDS DOMAIN                                                      │
└──────────────────────────────────────────────────────────────────────────────┘

Patient Record
│
└── Medical Entry
    ├── Entry Type
    ├── Source Provider
    ├── Created Timestamp
    ├── Recorded Timestamp
    ├── Critical Flag
    ├── Version Information
    └── Entry Metadata

Relationships:
Patient Record (1) ────────< (N) Medical Entry
Provider (1) ────────< (N) Medical Entry



Medical Entry Types
──────────────────────────────────────────────────────────────────────────────

Diagnosis
├── Diagnosis Name
├── Diagnosis Code
├── Severity
├── Chronicity
└── Diagnosis Date

Prescription
├── Medication Name
├── Dosage
├── Frequency
├── Administration Route
├── Start Date
└── End Date

Lab Report
├── Test Name
├── Result Value
├── Unit
├── Reference Range
├── Interpretation
└── Report Date

Procedure
├── Procedure Name
├── Procedure Code
├── Outcome
└── Procedure Date

Clinical Note
├── Author
├── Note Content
├── Clinical Context
└── Creation Date

Relationships:
Medical Entry (1) ──────── (1) Diagnosis
Medical Entry (1) ──────── (1) Prescription
Medical Entry (1) ──────── (1) Lab Report
Medical Entry (1) ──────── (1) Procedure
Medical Entry (1) ──────── (1) Clinical Note



┌──────────────────────────────────────────────────────────────────────────────┐
│ DOCUMENTS & FILE STORAGE DOMAIN                                             │
└──────────────────────────────────────────────────────────────────────────────┘

Medical Document
├── Associated Medical Entry
├── File Name
├── MIME Type
├── File Size
├── Storage Path
├── Upload Timestamp
└── Checksum

Relationships:
Medical Entry (1) ────────< (N) Medical Document

Examples:
- Scanned Prescription
- Lab PDF
- Medical Image
- Discharge Summary
- External Report



┌──────────────────────────────────────────────────────────────────────────────┐
│ CONSENT & ACCESS CONTROL DOMAIN                                             │
└──────────────────────────────────────────────────────────────────────────────┘

Consent Record
├── Patient
├── Granted To
├── Scope
├── Effective Period
├── Revocation Information
└── Consent Metadata

Access Permission
├── User
├── Resource
├── Permission Type
├── Expiry
├── Status
└── Permission Metadata

Relationships:
Patient (1) ────────< (N) Consent Record
User (1) ────────< (N) Access Permission

Important Flow:

Patient
    └── Gives Consent
            └── Creates/Updates Permission
                    └── Grants Access

Consent ≠ Permission

Consent represents:
    "Patient agreed"

Permission represents:
    "System currently allows access"



┌──────────────────────────────────────────────────────────────────────────────┐
│ AUDIT DOMAIN                                                                │
└──────────────────────────────────────────────────────────────────────────────┘

Audit Event
├── Actor
├── Action
├── Resource Type
├── Resource Identifier
├── Timestamp
├── Outcome
└── Additional Metadata

Relationships:
User (1) ────────< (N) Audit Event

Examples:
- Login
- Logout
- Record Viewed
- Record Uploaded
- Consent Granted
- Consent Revoked
- Permission Changed
- Duplicate Resolved

Properties:
- Append Only
- Immutable
- Never Deleted
- Never Updated



┌──────────────────────────────────────────────────────────────────────────────┐
│ NOTIFICATION DOMAIN                                                         │
└──────────────────────────────────────────────────────────────────────────────┘

Notification
├── Recipient
├── Message
├── Type
├── Read Status
└── Timestamp

Notification Preference
├── User
├── Channel
└── Enabled State

Relationships:
User (1) ────────< (N) Notification
User (1) ────────< (N) Notification Preference



┌──────────────────────────────────────────────────────────────────────────────┐
│ DATA QUALITY DOMAIN                                                         │
└──────────────────────────────────────────────────────────────────────────────┘

Duplicate Review Item
├── Candidate Records
├── Similarity Reason
├── Review Status
└── Resolution

Data Quality Flag
├── Affected Record
├── Flag Type
├── Severity
└── Resolution Status

Relationships:
Patient Record (1) ────────< (N) Data Quality Flag
Patient Record (1) ────────< (N) Duplicate Review Item



┌──────────────────────────────────────────────────────────────────────────────┐
│ ANALYTICS DOMAIN                                                            │
└──────────────────────────────────────────────────────────────────────────────┘

Summary Insight
├── Patient
├── Insight Type
├── Generated Data
├── Time Window
└── Generation Timestamp

Relationships:
Patient (1) ────────< (N) Summary Insight

Examples:
- Blood Pressure Trend
- HbA1c Trend
- Medication Adherence Summary
- Visit Frequency
- Upload Statistics

NOTE:
Analytics data is DERIVED DATA.
Primary medical information always remains in Medical Entries.



================================================================================
CORE RELATIONSHIP FLOW
================================================================================

User
│
├── Patient
│      │
│      └── Patient Record
│              │
│              ├── Medical Entries
│              │      ├── Diagnosis
│              │      ├── Prescription
│              │      ├── Lab Report
│              │      ├── Procedure
│              │      └── Clinical Note
│              │
│              ├── Consent Records
│              ├── Access Permissions
│              ├── Data Quality Flags
│              └── Duplicate Reviews
│
├── Provider Staff
│      │
│      └── Provider
│              │
│              └── Creates Medical Entries
│
├── Notifications
│
└── Audit Events



================================================================================
KEY ARCHITECTURAL DECISIONS & RATIONALE
================================================================================

1. MEDICAL ENTRY SUPER-TYPE MODEL
---------------------------------
Decision:
    One common Medical Entry entity with specialized subtypes.

Why:
    - Fast patient timelines
    - Strongly typed clinical data
    - Better normalization
    - Easier analytics
    - Easier future expansion

Avoids:
    Massive JSON blobs
    Huge UNION queries



2. CONSENT AND PERMISSIONS ARE SEPARATE
---------------------------------------
Decision:
    ConsentRecord and AccessPermission are distinct entities.

Why:
    Consent = legal/administrative agreement
    Permission = technical enforcement mechanism

Benefits:
    - Better auditability
    - Easier revocation logic
    - Cleaner authorization model



3. PATIENT RECORD AS AGGREGATE ROOT
-----------------------------------
Decision:
    All medical information lives beneath Patient Record.

Why:
    - Single source of truth
    - Easier ownership
    - Easier future merging/importing
    - Cleaner domain boundaries



4. FILES ARE NOT STORED IN DATABASE
-----------------------------------
Decision:
    Store only metadata in database.

Actual files:
    Local Storage Adapter

Benefits:
    - Smaller database
    - Faster backups
    - Easier migration to S3 later



5. APPEND-ONLY AUDIT LOG
------------------------
Decision:
    Audit events are immutable.

Why:
    Healthcare systems require traceability.

Benefits:
    - Compliance ready
    - Easier investigations
    - Better security posture



6. ANALYTICS IS DERIVED DATA
----------------------------
Decision:
    Never store analytics as primary medical data.

Why:
    Analytics can always be regenerated.

Benefits:
    - Prevents duplication
    - Maintains data integrity
    - Simplifies updates



7. MODULAR DOMAIN DESIGN
------------------------
Modules:
    Auth
    Users
    Patients
    Providers
    Records
    Consent
    Audit
    Notifications
    Analytics

Why:
    - Matches UML
    - Matches business domains
    - Easier testing
    - Easier future service extraction



8. ADAPTER-BASED INFRASTRUCTURE
-------------------------------
StorageProvider
NotificationProvider
IdentityProvider

Current:
    Local Storage
    In-App Notifications
    Email OTP

Future:
    S3
    MinIO
    Garage
    Email
    SMS
    ABHA

Business logic never changes when providers change.



9. SEARCH-FIRST DATA MODEL
--------------------------
Design optimized for:

Doctor Queries:
    "Show diabetes history"
    "Show all HbA1c results"
    "Show current medications"

Patient Queries:
    "Show my timeline"
    "Who accessed my records?"

Provider Queries:
    "Show uploaded reports"
    "Resolve duplicate records"

This is why structured subtype tables exist instead of storing
everything as unstructured JSON.
