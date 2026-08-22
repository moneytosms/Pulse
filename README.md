# Pulse

A lifelong electronic health record platform. Patients own their medical history; providers contribute to it; clinicians read it only with the patient's consent, and every access is recorded.

Built for an Indian demographic, in English, Hindi, Tamil and Malayalam. An academic project — it never touches real patient data — held to real engineering practice.

## Status

Architecture and planning are complete. Phase 1 implementation has not started.

| | |
|---|---|
| Architecture | Locked. See [`docs/architecture.md`](docs/architecture.md) |
| Domain model | Locked. See [`docs/domain-model.md`](docs/domain-model.md) |
| API contract | Locked. See [`docs/api-conventions.md`](docs/api-conventions.md) |
| Decisions | 15 ADRs in [`docs/adr/`](docs/adr/) |
| Delivery plan | [`docs/delivery-plan.md`](docs/delivery-plan.md) |
| Code | Not yet scaffolded |

## Quickstart

Once the Phase 0 scaffold lands, the whole system comes up on any machine with Docker:

```bash
git clone https://github.com/moneytosms/Pulse.git
cd Pulse
docker compose up
```

That must produce a working, **seeded** system — app on `:80`, Mailpit's inbox on `:8025`. It is the scaffold's acceptance test, not an aspiration.

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
