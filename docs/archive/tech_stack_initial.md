> **ARCHIVED — superseded by [`docs/architecture.md`](../architecture.md).**
>
> This was the initial technology proposal. It is kept for provenance only.
> Several things here were changed by the architecture tickets on
> [the map](https://github.com/moneytosms/Pulse/issues/1) — notably the auth model
> (this document implies passwordless email OTP; Pulse uses password-primary auth with
> OTP for verification and step-up), the `IdentityProvider` interface (two calls, not one),
> and the "stateless backend" goal (rejected in favour of Redis-backed sessions, ADR-0003).
>
> **Do not follow this document.**

---

Pulse Technical Architecture & Technology Stack

Version 1.0 - Implementation Architecture Proposal


---

1. Overview

Pulse is a unified lifelong electronic health record (EHR) platform consisting of:

Patient Portal

Clinician Portal

Provider Upload Portal

Administrative Dashboard

Audit & Compliance System

Consent & Access Control System


The architecture prioritizes:

Simplicity

Portability

Clear separation of concerns

Maintainability

Future scalability


while remaining deployable as a single Docker Compose stack for development, testing, and demonstrations.


---

2. Architectural Principles

The system will follow:

Modular Monolith Architecture

Pulse will be implemented as a modular monolith rather than a microservice architecture.

Each business domain is isolated into its own module with clearly defined interfaces.

Benefits:

Easier development

Lower operational complexity

Easier debugging

Faster iteration

Clear migration path to microservices if required


Modules communicate through service interfaces rather than direct database access.


---

Domain Driven Separation

The backend is organized around business domains rather than technical layers.

Auth
Users
Records
Consent
Audit
Notifications
Analytics
Administration

This aligns directly with the system requirements and UML diagrams.


---

Dependency Inversion Principle

Business logic must never depend on infrastructure implementations.

Core services depend on abstractions (interfaces), while infrastructure components implement those abstractions.

This allows storage providers, notification providers, and identity providers to be replaced without modifying business logic.


---

3. Technology Stack

Frontend

Framework

Next.js 16
React 19
TypeScript

Styling

Tailwind CSS
Radix UI

Forms & Validation

React Hook Form
Zod

Visualization

Recharts

Used for:

Health trends

Analytics dashboards

Record summaries



---

Backend

Framework

FastAPI
Python 3.13

Data Validation

Pydantic v2

ORM

SQLAlchemy 2

Database Migrations

Alembic


---

Database

Primary Database

PostgreSQL 18

Used for:

User management

Health records

Permissions

Audit logs

Notifications

Analytics metadata



---

Cache

Redis

Used for:

OTP storage

Rate limiting

Temporary tokens

Session invalidation


Not used as a primary datastore.


---

Storage

Current Implementation

Local Filesystem Storage

Files stored through mounted Docker volumes.

Examples:

/uploads/reports
/uploads/scans
/uploads/prescriptions

The database stores only metadata and references.


---

Deployment

Containerization

Docker
Docker Compose

Services:

frontend
backend
postgres
redis


---

4. Backend Module Structure

backend/

app/

├── core/
├── db/

├── modules/

│   ├── auth/
│   ├── users/
│   ├── records/
│   ├── consent/
│   ├── audit/
│   ├── notifications/
│   ├── analytics/
│   ├── providers/
│   └── admin/

├── adapters/

│   ├── storage/
│   ├── notification/
│   └── identity/

└── uploads/

Each module contains:

routes.py
service.py
schemas.py
models.py
repository.py


---

5. Adapter Architecture

A key architectural goal is ensuring that external systems can be replaced without modifying business logic.


---

Storage Adapter

Interface

class StorageProvider:
    upload()
    download()
    delete()

Current Implementation

LocalStorageProvider

Future Implementations

S3StorageProvider
MinIOStorageProvider
GarageStorageProvider
AzureBlobStorageProvider

Business services interact only with StorageProvider.


---

Notification Adapter

Interface

class NotificationProvider:
    send()

Current Implementation

InAppNotificationProvider

Future Implementations

EmailNotificationProvider
SMSNotificationProvider
PushNotificationProvider

The notification system remains unchanged regardless of delivery mechanism.


---

Identity Provider Adapter

Interface

class IdentityProvider:
    verify()

Current Implementation

EmailOTPIdentityProvider

Future Implementations

ABHAIdentityProvider
GovernmentHealthIDProvider
ExternalSSOProvider

This allows future integration with healthcare identity systems without rewriting authentication logic.


---

6. Repository Pattern

Business services should not directly interact with SQLAlchemy models.

Repositories abstract persistence concerns.

Example:

class PatientRepository:
    get_by_id()
    create()
    update()

Benefits:

Easier testing

Easier migration

Reduced coupling



---

7. Service Layer Pattern

All business logic resides within service classes.

Example:

ConsentService
AuditService
RecordService
AnalyticsService

Responsibilities:

Validation

Permission checks

Business rules

Workflow orchestration


Services must not contain framework-specific logic.


---

8. Authorization Model

Role-Based Access Control (RBAC)

Supported roles:

PATIENT
CLINICIAN
PROVIDER_STAFF
ADMINISTRATOR

Authorization checks occur through a centralized permission service.

Example:

PermissionService.can_view_record()
PermissionService.can_upload()

This prevents permission logic from being duplicated across endpoints.


---

9. Audit Logging Strategy

Audit logging is treated as a first-class architectural concern.

Every sensitive action generates an audit event.

Examples:

Login
Logout
Record View
Record Upload
Permission Grant
Permission Revoke
Role Change
Duplicate Resolution

Audit logs are append-only.

Existing records are never modified.


---

10. Future Scalability Strategy

Although Pulse is initially deployed as a modular monolith, several architectural decisions prepare the system for future scaling.


---

Stateless Backend

The backend should not store user session state locally.

This allows:

Multiple API instances
Load balancing
Horizontal scaling

without code changes.


---

Infrastructure Abstractions

The following are already abstracted:

Storage
Notifications
Identity Verification

New providers can be added through adapters.


---

Module Boundaries

Future service extraction becomes straightforward.

Possible future services:

Audit Service
Notification Service
Analytics Service
Identity Service

Each already exists as an independent module.


---

API First Design

All functionality is exposed through REST APIs.

Future clients can include:

Mobile Applications
Provider Integration Systems
Government Health Platforms
External Analytics Tools

without modifying core business logic.


---

11. Deployment Strategy

Development, testing, and demonstrations use:

docker compose up -d

The same deployment stack should run on:

Ouranos

Personal laptops

University lab machines

Cloud VPS instances


without configuration changes.

The system should remain self-contained and portable, allowing demonstrations to be performed on any machine capable of running Docker.


---

12. Summary

Pulse will be implemented as a modular monolith using FastAPI, PostgreSQL, Redis, and Next.js, with strong emphasis on:

Domain separation

Dependency inversion

Adapter-based integrations

Repository and service layer patterns

Auditability

Future extensibility


This architecture keeps the current implementation simple enough for a semester project while establishing clear boundaries and abstractions that support future growth, external integrations, and migration to larger-scale deployments if required.
