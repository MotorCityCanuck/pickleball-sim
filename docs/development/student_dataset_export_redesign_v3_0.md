# Student Dataset Export Redesign Specification
# Version 3.0

## Revision History

### Version 3.0 Enhancements
- Added Dimension Key Stability Requirements
- Added Entity Identifier Governance Rules
- Added Table-Level Export Contract Appendix
- Added Student Merge/Upsert Expectations
- Added Incremental Processing Design Guidance

---

# PURPOSE

This specification defines the authoritative export architecture for all student-facing NAPA datasets.

The objective is to provide a realistic data engineering experience while avoiding unnecessary implementation complexity.

Students must be able to:

- Build repeatable ingestion pipelines
- Process monthly data increments
- Detect and remediate data quality issues
- Maintain analytical environments over time

Students should not be required to implement enterprise-grade CDC, streaming architectures, or complex dimensional versioning.

---

# DIMENSION KEY STABILITY REQUIREMENTS

## Design Principle

Entity identifiers must remain stable throughout the entire lifecycle of a generation run.

A Player exported in:

- Initial Release
- Month 13 Increment
- Month 14 Increment
- Month 15 Increment

must retain the same identifier in every export.

The export process shall never regenerate identifiers during incremental releases.

---

## Stable Identifier Requirements

The following identifiers must be globally unique and persistent:

| Entity | Key |
|----------|----------|
| Player | player_id |
| Team | team_id |
| Club | club_id |
| Region | region_id |
| Match | match_id |
| Tournament | tournament_id |
| Assessment | assessment_id |
| Rating Event | rating_event_id |

These identifiers become the authoritative merge keys for student solutions.

---

## Surrogate Key Governance

If surrogate keys exist internally:

- They must remain stable.
- They must not be regenerated.
- They must not change between exports.

The same source entity must always produce the same exported identifier.

---

# STUDENT PROCESSING MODEL

Students should assume:

Initial Release:

- Full warehouse bootstrap
- Initial table creation
- Initial data quality profiling

Monthly Releases:

- Incremental processing
- Fact appends
- Historical record appends
- Dimension upserts

Students should not assume:

- Full dataset reloads
- Reprocessing all history every month

---

# TABLE-LEVEL EXPORT CONTRACT

This section serves as the authoritative definition of export behavior.

---

## Players

Initial Release

Contains:

- All Players

Monthly Release

Contains:

- New Players
- Updated Players referenced by monthly activity

Student Action

- Merge / Upsert

---

## Teams

Initial Release

Contains:

- All Teams

Monthly Release

Contains:

- New Teams
- Updated Teams referenced by monthly activity

Student Action

- Merge / Upsert

---

## Clubs

Initial Release

Contains:

- All Clubs

Monthly Release

Contains:

- New Clubs
- Updated Clubs referenced by monthly activity

Student Action

- Merge / Upsert

---

## Player Registrations

Initial Release

Contains:

- Historical registrations through Month 12

Monthly Release

Contains:

- Registration changes occurring during release month

Student Action

- Merge / Upsert

---

## Club Memberships

Initial Release

Contains:

- Historical membership records through Month 12

Monthly Release

Contains:

- Membership changes occurring during release month

Student Action

- Merge / Upsert

---

## Team Memberships

Initial Release

Contains:

- Historical team membership records through Month 12

Monthly Release

Contains:

- Membership changes occurring during release month

Student Action

- Merge / Upsert

---

## Matches

Initial Release

Contains:

- Months 1-12 Matches

Monthly Release

Contains:

- Release Month Matches Only

Student Action

- Append

---

## Match Teams

Monthly Release

Contains:

- Release Month records only

Student Action

- Append

---

## Match Players

Monthly Release

Contains:

- Release Month records only

Student Action

- Append

---

## Match Games

Monthly Release

Contains:

- Release Month records only

Student Action

- Append

---

## Player Rating History

Initial Release

Contains:

- Rating history Months 1-12

Monthly Release

Contains:

- Rating events generated during release month

Student Action

- Append

---

## Player Assessment History

Initial Release

Contains:

- Assessment history Months 1-12

Monthly Release

Contains:

- Assessment records generated during release month

Student Action

- Append

---

# RELEASE MANIFEST REQUIREMENTS

Every release must contain:

```json
{
  "release_sequence_number": 1,
  "release_type": "initial_snapshot",
  "release_month": null,
  "included_months": [1,2,3,4,5,6,7,8,9,10,11,12],
  "load_strategy": "full_load"
}
```

Monthly example:

```json
{
  "release_sequence_number": 4,
  "release_type": "monthly_incremental",
  "release_month": 15,
  "included_months": [15],
  "load_strategy": "incremental_load"
}
```

---

# RECOMMENDED EXPORT METADATA

Every exported dataset should include:

- release_sequence_number
- release_month
- export_timestamp

Benefits:

- Easier lineage tracking
- Easier troubleshooting
- Easier pipeline automation
- Simplified auditability

---

# FOLDER STRUCTURE

student_export/
├── initial/
│   └── napa_initial_history/
│       └── tainted/
└── monthly/
    ├── napa_increment_2026_01/
    │   └── tainted/
    ├── napa_increment_2026_02/
    │   └── tainted/
    └── napa_increment_2026_03/
        └── tainted/

Students receive only tainted datasets.

---

# ACCEPTANCE TESTS

8 Months

Expected:

- 1 Initial Release
- 0 Monthly Releases

12 Months

Expected:

- 1 Initial Release
- 0 Monthly Releases

15 Months

Expected:

- Initial Release (Months 1-12)
- Increment Month 13
- Increment Month 14
- Increment Month 15

Release Sequence Numbers:

1, 2, 3, 4

---

# IMPLEMENTATION GUIDANCE FOR CODEX

The export service shall:

1. Determine month count automatically.
2. Create release plan automatically.
3. Generate initial release including clean and tainted
4. Generate monthly increment releases including clean and tainted subfolders for each month.
5. Assign release sequence numbers.
6. Preserve identifier stability.
7. Produce deterministic outputs.
8. Generate manifests automatically.

This document shall be treated as the authoritative export contract for all student-facing datasets.
