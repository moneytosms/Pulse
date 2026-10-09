# Pulse

A lifelong electronic health record platform. Patients own their medical history; providers contribute to it; clinicians read it only with the patient's consent, and every access is recorded.

Built for an Indian demographic, in English, Hindi, Tamil and Malayalam. An academic project — it never touches real patient data — held to real engineering practice.

## Status

**Records, consent and the demo portals are implemented.** The stack includes entry filing/corrections, persistent documents, scoped consent and emergency access, audit history, localized notifications, computed analytics and administrator duplicate review. See [`docs/verification-and-operations.md`](docs/verification-and-operations.md) for checks, operational limits and remaining product workflows.

| | |
|---|---|
| Architecture | Locked. See [`docs/architecture.md`](docs/architecture.md) |
| Domain model | Locked. See [`docs/domain-model.md`](docs/domain-model.md) |
| API contract | Locked. See [`docs/api-conventions.md`](docs/api-conventions.md) |
| Decisions | 16 ADRs in [`docs/adr/`](docs/adr/) |
| Delivery plan | [`docs/delivery-plan.md`](docs/delivery-plan.md), tracked on [#17](https://github.com/moneytosms/Pulse/issues/17) |
| Build order | [#22](https://github.com/moneytosms/Pulse/issues/22) — every step, its blocker, and who waits on it |
| Code | `backend/` (FastAPI, real-database integration tests) · `frontend/` (Next.js) · `seed/` (Synthea + Indian overlay) |

## Quickstart

The whole system comes up on any machine with Docker:

```bash
git clone https://github.com/moneytosms/Pulse.git
cd Pulse
docker compose up
```

On first boot the backend runs migrations and seeds identity data. Then:

- App: `http://localhost` — try `/en/register`, or `/en/login`
- Mailpit inbox (default local verification emails): `http://localhost:8025`; Gmail SMTP setup is in [`docs/demo.md`](docs/demo.md)
- Seeded patient login: `demo.patient.hi@example.com` / `Pulse@demo1` (also `demo.patient.en@example.com`; see [`seed/README.md`](seed/README.md))

Demo journey: provider files an entry → patient grants clinician access with password confirmation → clinician reads → patient reviews access history → patient revokes → clinician is locked out. The live browser suite rehearses this through Caddy.

## Shape

A modular monolith: one FastAPI application, one PostgreSQL database, organised by business domain.

```
browser → Caddy ┬→ /api/*  FastAPI ┬→ PostgreSQL
                │                  └→ Redis (sessions, rate limits, short-lived tokens)
                └→ /*      Next.js
```

Modules: `auth · users · patients · providers · records · consent · audit · notifications · analytics · admin`

## Reading order

Start with [`CONTEXT.md`](CONTEXT.md) — the glossary. Terms in this project mean specific things, and two distinctions carry the whole design: **Consent is not Permission**, and **the interface is localised, clinical data is not**.

Then [`docs/architecture.md`](docs/architecture.md) for how it is built, [`docs/domain-model.md`](docs/domain-model.md) for the entities, [`docs/api-conventions.md`](docs/api-conventions.md) for what every endpoint looks like, and [`docs/adr/`](docs/adr/) for the decisions that were expensive enough to write down.

[`docs/learnings.md`](docs/learnings.md) explains every non-obvious pattern in the codebase — what it is, why it is here, what it replaces. The point of it is that anyone on the team can explain any part of the project, including the parts they did not type.

## Team

| | |
|---|---|
| Shivansh | Database — models, migrations, repositories, seed data |
| Akshay | Backend — FastAPI, services, schemas, auth, adapters |
| Bharadwaj | Frontend — Next.js, design system, i18n, four portals |
| Srimoney | Platform, CI, integration, review, deployment |

Work is sliced in [`docs/delivery-plan.md`](docs/delivery-plan.md).

## Not in scope

ABHA/ABDM live integration · real SMS or email delivery · DPDP certification · native mobile apps · FHIR export · OCR of uploaded documents · ML · multi-tenancy · Kubernetes.

The design is DPDP-shaped and takes ABDM's consent framework as inspiration. Neither is a compliance claim.
