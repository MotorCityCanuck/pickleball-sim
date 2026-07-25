# Team Identity and Student Export Refactor Handoff

## Purpose

This document summarizes the recent changes to team creation logic, related
database/schema contracts, and the student-facing data export. It is intended as
handoff context for a Codex agent working in another repository so it can assess
whether downstream refactoring is required.

The relevant recent commits in this repository are:

- `8fabd77` - `feat: Add canonical team identity registry`
- `a5009ff` - `feat: Split team identity from team division`
- `cf8bbfe` - `feat: Persist ad hoc match teams during match generation`
- `1620372` - `feat; Store match winners as persistent team ids`
- `2929255` - `feat: Add team identity contract regression tests`
- `0ff2334` - `bug: Fix ad hoc team effective dates on pair reuse`
- `742e146` - `feat: Align student exports with persistent team identity`

## Executive Summary

The generator now treats every two-player doubles pair as a persistent team
identity. A pair of players should map to at most one `teams.id` within a
generation run, regardless of whether the pair originated from structured team
formation or an ad hoc match.

The old model overloaded `teams.team_type` with doubles divisions such as
`mens_doubles`, `womens_doubles`, `mixed_doubles`, and `open_doubles`. The new
model splits that into two fields:

- `teams.team_type`: identity class, currently `competitive` or `ad_hoc`.
- `teams.team_division`: doubles division, currently `mens_doubles`,
  `womens_doubles`, `mixed_doubles`, or `open_doubles`.

Match sides now always carry a persistent team reference through
`match_teams.source_team_id`. In the student export this is exposed as
`match_teams.team_id`. Match winners are now stored as persistent team ids in
`matches.winning_team_id`, not as `match_teams.id` row ids.

The student-facing dataset schema version is now `1.5`.

## Team Identity Contract

The core behavior is implemented in
`backend/app/generators/team_identity.py`.

The `TeamIdentityRegistry` is generation-run scoped and keyed by a canonical
unordered player pair:

```text
player_pair_key(20, 10) == (10, 20)
player_pair_key(10, 20) == (10, 20)
player_pair_key(10, 10) raises ValueError
```

Required behavior:

- Each unordered two-player pair has at most one `teams.id` per
  `generation_run_id`.
- Pair order is irrelevant for identity lookup.
- A pair cannot exist as both a competitive team and an ad hoc team.
- If a pair already exists, the existing team identity is reused.
- `team_type` does not change when an existing pair is reused.
- `team_division` records the doubles composition/competition category.
- Each identity creates exactly two `team_memberships` rows when first created.

The registry loads existing two-player teams by joining `teams` to
`team_memberships`, then rejects duplicate identities for the same pair.
There is not a simple database unique constraint for the unordered pair because
the identity is derived from two `team_memberships` rows. The uniqueness
contract is currently enforced in generator/application logic.

## Competitive Team Creation

Structured team generation is implemented in
`backend/app/generators/teams.py`.

Important changes:

- The weighted configuration still uses the existing
  `team_formation.team_type_weights` payload, but those values now represent
  `team_division` choices rather than `team_type` values.
- Newly formed structured teams are created through `TeamIdentityRegistry`.
- Structured teams are created with:
  - `team_type = 'competitive'`
  - `team_division = sampled division`
  - `team_status = 'active'`
- Before creating a structured team, the generator checks whether the unordered
  pair already has an identity. If it does, the generator does not create a
  duplicate competitive team.
- Team lifecycle state still lives in `team_status`, `formation_date`, and
  `dissolution_date`; it should not be inferred from or written into
  `team_type`.

Refactor implication: any downstream code that still interprets
`teams.team_type` as a division must be updated to use `team_division`.

## Ad Hoc Match Team Creation

Ad hoc match-side generation is implemented in
`backend/app/generators/matches.py`.

Important changes:

- Ad hoc sides are no longer transient negative-id candidates.
- When the match generator samples an ad hoc two-player side, it resolves that
  side through `TeamIdentityRegistry.get_or_create_team`.
- If the unordered pair is new, the match generator creates:
  - one `teams` row with `team_type = 'ad_hoc'`;
  - a derived `team_division`;
  - two `team_memberships` rows;
  - one persistent `teams.id` reused by future matches for that pair.
- If the unordered pair already exists, the existing `teams.id` is reused.
- `pairing_source` remains a match-side provenance value:
  - `competitive_team` for competitive team identities;
  - `ad_hoc` for ad hoc team identities.
- The active competitive team pool now loads only teams where
  `Team.team_type == 'competitive'`.
- Opponent selection groups by `team_division`, not `team_type`.

An ad hoc reuse edge case was fixed: if an ad hoc pair is first created for a
later match date and then reused for an earlier date during generation,
`TeamIdentityRegistry` moves the ad hoc team's `formation_date` and membership
`joined_date` back to the earlier date. This backdating behavior applies only
to `team_type = 'ad_hoc'`; competitive teams are not backdated on reuse.

## Match Winner Semantics

`matches.winning_team_id` now stores the persistent winning `teams.id`.

Previously, some code treated `matches.winning_team_id` as a reference to
`match_teams.id`, the per-match side row. That is no longer correct.

Current internal behavior:

- Each `MatchTeam` row has a non-null `source_team_id`.
- After scores are generated, `Match.winning_team_id` is set to the winning
  side's `MatchTeam.source_team_id`.
- Rating updates compare `match.winning_team_id` to
  `match_team.source_team_id` when deciding whether that side won.
- Realism audit queries map the winning side by comparing
  `match_teams.source_team_id` to `matches.winning_team_id`.

Important nuance:

- In the SQLAlchemy model, `Match.winning_team_id` remains a plain
  `BigInteger`, not an ORM `ForeignKey`.
- In the logical/export contract, it should be treated as a persistent
  `teams.id`.
- It must match one of the two participating match sides' persistent team ids
  for the same match.

Refactor implication: downstream code should not join
`matches.winning_team_id` to `match_teams.id`. It should join to `teams.id`, or
validate it against `match_teams.source_team_id`/exported
`match_teams.team_id` for the same match.

## Database and ORM Changes

Authoritative files:

- `backend/app/models/teams.py`
- `backend/app/models/match_teams.py`
- `backend/app/models/matches.py`
- `backend/schema.sql`

### `teams`

`teams.team_type` changed meaning and constraints:

```sql
team_type VARCHAR(30) DEFAULT 'competitive' NOT NULL
CHECK (team_type IN ('competitive', 'ad_hoc'))
```

`teams.team_division` was added:

```sql
team_division VARCHAR(50) DEFAULT 'open_doubles' NOT NULL
CHECK (team_division IN ('mens_doubles', 'womens_doubles', 'mixed_doubles', 'open_doubles'))
```

Indexes include:

```sql
idx_teams_type
idx_teams_division
idx_teams_status
idx_teams_country
idx_teams_formation_date
```

### `match_teams`

`match_teams.source_team_id` is now required:

```sql
source_team_id BIGINT NOT NULL REFERENCES teams(id)
```

This remains the internal physical column name. The student export aliases it
to `team_id`.

### `matches`

`matches.winning_team_id` stores the persistent winning team id. It is still a
plain `BIGINT` in the core schema and ORM model, so any referential validation
must be handled in application/export validation unless that open schema
decision is later changed.

### Existing Data Migration Considerations

This repository's checked schema reflects the new contract, but there is no
general-purpose migration script in the recent change set for arbitrary
pre-change databases. A downstream repo with existing data should evaluate:

- adding and backfilling `teams.team_division` from the old division-valued
  `teams.team_type`;
- converting `teams.team_type` to `competitive` or `ad_hoc`;
- populating every `match_teams.source_team_id`;
- rewriting `matches.winning_team_id` values that still point to
  `match_teams.id` so they point to the corresponding persistent team id;
- detecting duplicate unordered player-pair identities before enforcing the new
  application contract.

## Student Dataset Export Changes

Authoritative files:

- `backend/app/exports/student_dataset/projection.py`
- `backend/app/exports/student_dataset/queries.py`
- `backend/app/exports/student_dataset/validation.py`
- `backend/app/exports/student_dataset/writer.py`
- `docs/development/student_facing_dataset_build_specification.md`
- `docs/development/student_facing_dataset_data_dictionary.md`
- `docs/development/napa_parquet_inventory.md`

The student-facing export contract was bumped to:

```text
STUDENT_DATASET_SCHEMA_VERSION = "1.5"
```

The release still emits 13 Parquet files in this order:

```text
clubs
club_memberships
match_games
match_team_players
match_teams
matches
monthly_batches
player_assessment_history
player_master
player_registrations
regions
team_memberships
teams
```

### `teams.parquet`

The exported `teams` columns now include `team_division`:

```text
id
team_type
team_division
team_status
country_code
formation_date
dissolution_date
```

`team_type` is now `competitive` or `ad_hoc`. Any consumer expecting
`team_type` to contain `mens_doubles`, `womens_doubles`, `mixed_doubles`, or
`open_doubles` must be updated.

### `match_teams.parquet`

The exported columns are:

```text
id
match_id
team_number
team_id
team_score
average_team_rating
```

`team_id` is not an internal ORM column on `MatchTeam`. It is projected as:

```python
MatchTeam.source_team_id.label("team_id")
```

Export relationship validation now requires:

```text
match_teams.match_id -> matches.id
match_teams.team_id -> teams.id
```

### `matches.parquet`

`matches.winning_team_id` now references the persistent `teams.id`, not
`match_teams.id`.

Export relationship validation now treats:

```text
matches.winning_team_id -> teams.id
```

The staged release validation also checks the stronger same-match condition:
`matches.winning_team_id` must match one of the two `match_teams.team_id`
values for that match when it is non-null.

### Incremental Export Inclusion Rules

The incremental export logic was adjusted so match fact rows continue to have
their required team context.

Key changes in `backend/app/exports/student_dataset/queries.py`:

- `_fact_match_team_source_team_ids(context)` returns the persistent team ids
  from match sides included in the fact window.
- `_incremental_team_ids(context)` now includes:
  - changed teams;
  - teams referenced by changed team memberships;
  - teams referenced by included match sides.
- `_team_memberships_query(context)` now includes membership rows for teams
  referenced by included match sides, even when the membership row itself was
  not a direct delta row.
- `team_memberships` was removed from `_INCREMENTAL_DELTA_TABLES`; it now uses
  custom logic instead of only emitting direct row deltas.
- Snapshot builders explicitly include a full as-of-snapshot query for
  `team_memberships`.

Refactor implication: consumers of incremental releases should expect
`teams.parquet` and `team_memberships.parquet` to include contextual rows needed
by new match facts, not only directly changed rows.

## Data Quality Export Changes

The data-quality injection and validation code was updated for the new winner
semantics:

- Duplicate-like row injection no longer remaps `matches.winning_team_id` when
  cloning `match_teams` rows, because the winner id points to a persistent
  `teams.id`, not to cloned `match_teams.id`.
- Data-quality relationship validation can now validate relationships whose
  parent key is not the default primary key, such as
  `team_memberships.player_id -> player_master.player_id`.
- Required/categorical data-quality rules for `teams` now include
  `team_division`.

Relevant files:

- `backend/app/exports/data_quality/injector.py`
- `backend/app/exports/data_quality/validators.py`
- `backend/app/exports/data_quality/rules.py`

## Validation and Test Coverage

Regression coverage was added or updated in these areas:

- `backend/tests/test_team_generator.py`
  - canonical unordered pair keys;
  - duplicate pair reuse;
  - ad hoc backdating;
  - competitive teams not backdated;
  - structured teams use `team_type = 'competitive'`;
  - divisions are stored in `team_division`.
- `backend/tests/test_match_generator.py`
  - competitive match sides have source-team metadata;
  - ad hoc matches create/reuse persistent team identities;
  - `matches.winning_team_id` is one of the match side source team ids;
  - match-side players match the source team's memberships;
  - ad hoc divisions are populated.
- `backend/tests/test_rating_update_generator.py`
  - rating win detection uses persistent source team ids.
- `backend/tests/test_student_dataset_projection.py`
  - schema version is `1.5`;
  - match identity relationships use persistent team ids.
- `backend/tests/test_student_dataset_queries.py`
  - export queries project source team ids as `team_id`;
  - incremental exports include team and membership context for match facts.
- `backend/tests/test_student_dataset_writer.py`
  - staged release validation accepts nullable winner ids;
  - exported schema carries the persistent team-id relationships.
- `backend/tests/test_realism_audit.py`
  - realism audit winner-side joins use source team ids.

Useful targeted regression commands:

```bash
.venv/bin/pytest backend/tests/test_team_generator.py
.venv/bin/pytest backend/tests/test_match_generator.py
.venv/bin/pytest backend/tests/test_rating_update_generator.py
.venv/bin/pytest backend/tests/test_student_dataset_projection.py
.venv/bin/pytest backend/tests/test_student_dataset_queries.py
.venv/bin/pytest backend/tests/test_student_dataset_writer.py
.venv/bin/pytest backend/tests/test_data_quality_injection.py
.venv/bin/pytest backend/tests/test_realism_audit.py
.venv/bin/pytest backend/tests/test_tournament_team_loader.py
.venv/bin/pytest backend/tests/test_orm_consistency.py
```

## Known Compatibility Risks for the Other Repo

Check for any code that:

- Assumes `teams.team_type` contains division values.
- Filters competitive teams by `team_type IN ('mens_doubles', ...)`.
- Groups or displays divisions using `team_type`.
- Expects `match_teams.team_id` to be nullable.
- Expects internal ORM `MatchTeam.team_id` to exist; internally the field is
  still `source_team_id`.
- Joins `matches.winning_team_id` to `match_teams.id`.
- Assumes `matches.winning_team_id` changes when `match_teams` rows are cloned.
- Treats ad hoc match sides as transient pairings without rows in `teams` and
  `team_memberships`.
- Interprets a new `teams` row as necessarily a structured competitive team.
- Uses student export schema version `1.3` or `1.4` to infer current column
  contracts.
- Reads `teams.parquet` with a hardcoded six-column schema.
- Reads `match_teams.parquet` without a non-null `team_id` foreign key to
  `teams.parquet`.

## Specific Refactor Checklist

For downstream code, evaluate these changes:

1. Rename division-facing uses of `team_type` to `team_division`.
2. Preserve `team_type` only for identity class logic: `competitive` vs
   `ad_hoc`.
3. Update schema definitions, fixtures, mocks, seed data, and tests to include
   `teams.team_division`.
4. Ensure generated or imported `match_teams` rows always have a persistent
   team id.
5. If working with internal application tables, use
   `match_teams.source_team_id`.
6. If working with student export files, use exported `match_teams.team_id`.
7. Update winner joins from `matches.winning_team_id = match_teams.id` to either
   `matches.winning_team_id = teams.id` or
   `matches.winning_team_id = match_teams.team_id/source_team_id`.
8. Update data dictionaries, BI models, dbt models, notebooks, and QA checks to
   recognize `matches.winning_team_id -> teams.id`.
9. Add validation that every non-null match winner id appears among that match's
   two side team ids.
10. Update incremental export consumers to accept team and membership context
    rows emitted because a match fact references those teams.

## Local Caveat

The application export code and docs now describe schema version `1.5`, but the
standalone DuckDB release checker at
`scripts/student_dataset_duckdb_quality_check.sql` still contains older
expectations in the checked file, including a `schema_version_is_1_3` check and
an older `teams` column order that does not list `team_division`. If the other
repo relies on that checker or a copy of it, it should be updated before using
it as authoritative validation for current exports.

## Source of Truth Summary

Use these as the current contract:

- Team identity creation and reuse:
  `backend/app/generators/team_identity.py`
- Competitive team generation:
  `backend/app/generators/teams.py`
- Match/ad hoc team generation:
  `backend/app/generators/matches.py`
- ORM/database schema:
  `backend/app/models/teams.py`,
  `backend/app/models/match_teams.py`,
  `backend/app/models/matches.py`,
  `backend/schema.sql`
- Student export projection/query/validation:
  `backend/app/exports/student_dataset/projection.py`,
  `backend/app/exports/student_dataset/queries.py`,
  `backend/app/exports/student_dataset/validation.py`
- Student-facing documentation:
  `docs/development/student_facing_dataset_build_specification.md`,
  `docs/development/student_facing_dataset_data_dictionary.md`,
  `docs/development/napa_parquet_inventory.md`
