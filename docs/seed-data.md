# Seed Data

How Pulse's demo data is produced. The decision and its reasoning are in [ADR-0015](./adr/0015-synthea-plus-indian-overlay-seed-data.md); this document is the operational spec, including the two identity gaps that research closed on 2026-08-22.

**Pulse never holds real patient data.** Everything below is synthetic by construction.

## Pipeline

```
Synthea (pinned version + fixed seed)
   │  clinical content: conditions (SNOMED-CT), observations (LOINC), medications (RxNorm)
   ▼
Indian identity overlay (deterministic, same seed)
   │  names · phone numbers · addresses · medication brand names
   ▼
Duplicate planting
   │  known duplicate pairs + deliberate near-miss non-duplicates
   ▼
Committed dataset  ──▶  loader runs on first `docker compose up`
```

Both the Synthea invocation and the overlay are seeded, so the dataset is reproducible. It is committed rather than regenerated because Synthea is Java and `git clone && docker compose up` must work without a JDK.

The near-miss non-duplicates matter as much as the planted duplicates: with only true pairs planted, duplicate detection can be *demonstrated* but its precision cannot be *measured*. Two siblings with the same surname and adjacent dates of birth are the interesting case.

## Identity sources

| Field | Source |
|---|---|
| Names — Hindi, Tamil, Gujarati, Marathi, Odia, English | Faker's Indian locales (`hi_IN`, `ta_IN`, `gu_IN`, `mr_IN`, `or_IN`, `en_IN`) |
| Names — Malayalam | A Pulse-maintained provider. See below. |
| Addresses | data.gov.in Pincode Directory |
| Phone numbers | A Pulse sentinel prefix. See below. |
| Medication brands | `junioralive/Indian-Medicine-Dataset` |

## Gap 1 — Malayalam names

**Faker ships no `ml_IN` provider.** Verified against the `joke2k/faker` source on 2026-08-22: Indian person/address/phone providers cover `en_IN`, `gu_IN`, `hi_IN`, `mr_IN`, `or_IN` and `ta_IN` only. Mimesis has no Indian locales at all. No off-the-shelf Kerala name corpus was found with a licence clean enough to commit — the candidates were either too thin, unlicensed, or licence-ambiguous about their own upstream.

**What we do:** hand-curate a small word-list — given names split by gender, Hindu community surnames, Syrian Christian house names, Mappila Muslim given-name patterns — and wrap it as a Faker custom provider under a project-local `ml_IN` namespace, shaped exactly like Faker's own `or_IN` provider so the overlay calls it the same way it calls every other locale. Tens to low hundreds of entries, not thousands.

Personal names are facts and not independently copyrightable, so a hand-compiled list carries no licence encumbrance. The structural sources for Kerala naming conventions get cited in a code comment anyway — the same courtesy Faker extends to its own sources.

Model at least two of the three community naming patterns rather than a generic "first + last". Kerala's naming diversity is a realism detail worth having, and it is a natural source of extra near-duplicate patterns — the same person recorded once with house-name initials and once fully expanded.

## Gap 2 — phone numbers

**India has no reserved fictional number range.** There is no equivalent of North America's 555-01XX or Ofcom's drama numbers; TRAI and DoT have designated none. ITU-T's +991 trial mechanism exists but requires an ITU-member application and would not produce a `+91` number anyway. Research could not verify any specific unallocated mobile block, because every `.gov.in` primary source was blocked from the research environment — so that question is recorded as **unverified**, not answered.

Note in passing: repdigit numbers like `9999999999` are *not* safely fake — they are sold in India as premium "fancy numbers".

**What we do:** generate `+91 90000 XXXXX` — a fixed, Pulse-defined sentinel block with five random trailing digits. Structurally valid (correct length, valid first digit) so the app's own validation and duplicate matching still exercise realistic input, and trivially greppable in the codebase, in the database, and in any export.

**How this is stated in the submission, honestly:**

> This prefix is a Pulse convention, not an officially reserved range — India has no regulator-designated equivalent to NANP 555 or Ofcom's drama numbers. We chose a fixed, clearly non-organic prefix to minimise collision risk and make every seed phone number identifiable, but we cannot claim zero collision the way a US or UK project can.

Do not upgrade that wording to imply a reservation. If someone with access to `dot.gov.in` can check the National Numbering Plan for a genuinely unallocated block, the claim gets stronger; until then this is what is true.

## National identifiers

Pulse has no Aadhaar field and is not adding one. If a national identifier is ever added, seed values must have a **deliberately invalid Verhoeff check digit** — Aadhaar's checksum is public, so an invalid one is provably not a real number. Generating checksum-valid numbers would produce values indistinguishable from real ones outside UIDAI's database, which is exactly the thing not to do.
