# NAPA 5K Silver Null Source Analysis

## Purpose

This document records a source-side review of selected Silver-layer null
patterns reported for the NAPA 5K student dataset release. The goal is to
separate true source-data gaps from export-contract behavior and
Bronze-to-Silver transformation assumptions.

Target release reviewed:

```text
napa_5k equivalent local release:
data/student_dataset_exports/5k_12_months_to_test_new_team_membership_approach/20260724/132257Z/clean/5k_12_months_to_test_new_team_membership_approach_initial_history
```

Release metadata from `student_dataset_releases`:

```text
id: 130
generation_run_id: 86
release_name: 5k_12_months_to_test_new_team_membership_approach_initial_history
release_type: initial_snapshot
data_quality_level: none
status: succeeded
student_dataset_schema_version: 1.5
snapshot_end_exclusive: 2026-01-01
```

5K clean export row counts from `manifest.json`:

| Table | Rows |
|---|---:|
| `teams` | 82,463 |
| `team_memberships` | 164,926 |
| `club_memberships` | 5,958 |
| `player_registrations` | 6,229 |
| `player_master` | 6,229 |
| `regions` | 491 |
| `clubs` | 2,434 |
| `matches` | 70,867 |
| `match_teams` | 141,734 |
| `player_assessment_history` | 289,697 |

## Method

Reviewed:

- Source ORM/schema definitions:
  - `backend/app/models/teams.py`
  - `backend/app/models/team_memberships.py`
  - `backend/app/models/club_memberships.py`
  - `backend/app/models/player_registrations.py`
  - `backend/app/models/players.py`
  - `backend/app/models/regions.py`
  - `backend/app/models/clubs.py`
  - `backend/app/models/matches.py`
  - `backend/app/models/match_teams.py`
  - `backend/app/models/player_assessment_history.py`
  - `backend/schema.sql`
- Generator code:
  - `backend/app/generators/teams.py`
  - `backend/app/generators/matches.py`
  - `backend/app/generators/team_identity.py`
  - `backend/app/generators/players.py`
  - `backend/app/generators/ratings.py`
- Student export projection/query logic:
  - `backend/app/exports/student_dataset/projection.py`
  - `backend/app/exports/student_dataset/queries.py`
- Delivered 5K clean Parquet files using the project virtualenv's `pyarrow`.
- Current local Postgres backing database via read-only `psql` queries.

Important database caveat:

The local `student_dataset_releases` table still maps the reviewed 5K release to
generation run `86`, but the current backing source tables no longer contain
source rows for generation run `86`. The current populated source run is
generation run `88`, a 250K run. Therefore:

- 5K delivered-source-file behavior was verified directly from the exported
  Parquet files.
- Source schema and generator behavior were verified from code and current DB
  schema.
- Current DB source-row null checks were run against generation run `88` as a
  250K behavior comparator where useful.

## Executive Findings

Most reported 100% Silver null patterns are not source-export bugs. They are
caused by Bronze-to-Silver expecting renamed fields, derived fields, or
placeholder attributes that are not present in the current source contract.

One confirmed source-generation bug was found:

- `teams.country_code` is null for every ad hoc team because ad hoc team
  creation does not pass a `country_code` into `TeamIdentityRegistry`.

Several source attributes are available under different names:

- `team_memberships.membership_start_date` should map from
  source/export `team_memberships.joined_date`.
- `club_memberships.membership_end_date` should map from
  source/export `club_memberships.end_date`.
- `player_registrations.effective_start_date` should map from
  source/export `player_registrations.registration_month`.
- `players.preferred_side` has no source equivalent, but
  `player_master.dominant_hand` is populated.
- `matches.competition_category` has no source equivalent, but
  `matches.match_type` is populated.
- `player_assessment_history.assessment_confidence` should map from
  source/export `player_assessment_history.confidence_score`.

Several fields should be documented as intentionally unavailable from source:

- `players.preferred_side`
- `regions.active_flag`
- `clubs.active_flag`
- `teams.team_name`
- `matches.match_status`
- `match_teams.pre_match_team_rating`
- `match_teams.post_match_team_rating`
- `match_teams.rating_change`
- `player_assessment_history.assessor_source`
- registration interval/duration/status fields beyond the intake event

## Detailed Field Analysis and Recommended Actions

### 1. `teams.country_code`- fixed in Generator

| Item | Finding |
|---|---|
| Source DB column | Present: `teams.country_code` |
| Exported source-file column | Present: `teams.country_code` in `teams.parquet` |
| 5K export behavior | 70,727 nulls / 82,463 rows; 85.77% null |
| 5K breakdown | `competitive`: 11,736 rows, 0 null; `ad_hoc`: 70,727 rows, 70,727 null |
| 250K comparator | Run `88`: `competitive` 591,206 rows, 0 null; `ad_hoc` 3,556,007 rows, 100% null |
| Expected null behavior | Not expected for ad hoc teams; country is inferable from players/regions |
| Classification | Confirmed source-generation bug |
we
Root cause:

- Competitive teams are created in `backend/app/generators/teams.py` with
  `country_code=first_player.country_code`.
- Ad hoc teams are created in `backend/app/generators/matches.py` by
  `_ad_hoc_pair_candidate()`, which calls
  `team_registry.get_or_create_team(...)` without `country_code`.
- `TeamIdentityRegistry.get_or_create_team()` in
  `backend/app/generators/team_identity.py` accepts `country_code`, but it is
  optional and defaults to `None`.

Relevant code paths:

- `backend/app/generators/teams.py`: competitive team creation passes country.
- `backend/app/generators/matches.py`: ad hoc team creation omits country.
- `backend/app/generators/team_identity.py`: stores provided `country_code` on
  `Team`.
giv
Recommended actions:

1. Update `_ad_hoc_pair_candidate()` to pass a country code when creating ad hoc
   team identities.
2. Prefer deriving the country from the selected players' regions. Since
   `ActivePlayerCandidate` already carries `region_id`, either:
   - add `country_code` to `ActivePlayerCandidate` when active players are
     loaded, or
   - call the existing `country_code_for_region()` helper using the selected
     candidate region.
3. If both players have regions, validate or enforce same-country pairing for
   ad hoc teams, or define deterministic fallback behavior.
4. Add regression tests proving:
   - newly created ad hoc teams receive non-null `country_code`;
   - reused ad hoc identities keep the country;
   - generated `teams.country_code` is non-null for both competitive and ad hoc
     teams when player regions are known.
5. Consider a repair/backfill script for already delivered/generated datasets:
   join ad hoc teams through `team_memberships -> players -> regions` and set
   `teams.country_code` when all member regions agree.

### 2. `team_memberships.membership_start_date` - Fixed in pipeline

| Item | Finding |
|---|---|
| Source DB column | Not present under this name |
| Source DB equivalent | `team_memberships.joined_date` |
| Exported source-file column | `team_memberships.joined_date` |
| 5K export behavior | `joined_date`: 164,926 non-null / 164,926 rows |
| Expected null behavior | Silver `membership_start_date` should not be null if mapped from `joined_date` |
| Classification | Bronze-to-Silver transform naming issue |

Source contract:

`backend/app/models/team_memberships.py` defines:

```text
id
team_id
player_id
player_position
joined_date
left_date
```

`backend/app/exports/student_dataset/projection.py` exports:

```text
id
team_id
player_id
player_position
joined_date
left_date
```

Recommended actions:

1. Update Bronze-to-Silver mapping:

   ```text
   membership_start_date = joined_date
   ```

2. Keep `joined_date` in Bronze/raw as the source-native name for traceability.
3. Add a Silver audit expectation that `team_memberships.membership_start_date`
   is populated when `joined_date` is present.
4. Do not request a source generator change for this field unless the target
   canonical source contract is intentionally renamed.

### 3. `club_memberships.membership_end_date` - fixed in pipeline

| Item | Finding |
|---|---|
| Source DB column | `club_memberships.end_date` |
| Exported source-file column | `club_memberships.end_date` |
| 5K export behavior | `end_date`: 5,958 nulls / 5,958 rows |
| 250K comparator | Current DB run `88` club memberships: `end_date` 100% null |
| Expected null behavior | Expected for active/open-ended memberships |
| Classification | Source data is intentionally open-ended; Silver naming should map from `end_date` |

Source contract:

`backend/app/models/club_memberships.py` defines:

```text
start_date DATE NOT NULL
end_date DATE NULL
```

The export suppresses future end dates as null:

```text
end_date IS NULL OR end_date < snapshot_end_exclusive
```

The generator currently produces active memberships without end dates for this
release pattern.

Recommended actions:

1. Map Silver `membership_end_date` from source/export `end_date`.
2. Treat null `membership_end_date` as an active/open-ended membership, not as a
   data quality failure.
3. If the analytical model requires closed memberships, add a downstream
   derived as-of end date such as `coalesce(end_date, snapshot_end_exclusive)`,
   but do not overwrite the source end date.
4. Document that 5K, 50K, and 250K current-generation behavior may produce
   100% null `end_date` when no club membership churn is modeled.

### 4. `club_memberships.membership_duration_days` - resolved in pipeline

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Source components | `start_date`, `end_date`, release snapshot date |
| Expected null behavior | Null if Silver expects source field directly |
| Classification | Downstream derived field |

Recommended actions:

1. Derive in Silver or Gold, not in source extraction:

   ```text
   membership_duration_days =
     date_diff('day', start_date, coalesce(end_date, snapshot_end_exclusive))
   ```

2. Decide whether the duration should be as-of the snapshot date or null for
   open-ended memberships. Document that semantic explicitly.
3. Add a test case for open-ended memberships so duration is not accidentally
   left null unless that is the intended semantic.

### 5. `player_registrations.effective_start_date` - fixed in the pipelines

| Item | Finding |
|---|---|
| Source DB column | Not present under this name |
| Source DB equivalent | `player_registrations.registration_month` |
| Exported source-file column | `registration_month` |
| 5K export behavior | `registration_month`: 6,229 non-null / 6,229 rows |
| Expected null behavior | Silver field should be populated if it maps from `registration_month` |
| Classification | Bronze-to-Silver transform naming issue |  effective_start_date should be the first day of the registration_month

Recommended actions:

1. Update Silver mapping:

   ```text
   effective_start_date = registration_month
   ```

2. Keep source-native `registration_month` available in Bronze/raw lineage.
3. Add transform tests that fail if `effective_start_date` is null while
   `registration_month` is populated.

### 6. `player_registrations.effective_end_date` - fixed in pipeline

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Closest related source fields | `registration_month`, `registration_source`, `players.player_status` |
| Expected null behavior | Expected if treated as source field |
| Classification | Intentionally unavailable / downstream placeholder |

Source semantics:

`player_registrations` is an intake event table, not an interval table. It
records when a player was introduced to the system.

Recommended actions:

1. Do not expect this field from source.
2. If Silver requires interval semantics, derive them downstream from player
   lifecycle/status logic, not from `player_registrations`.
3. Leave `effective_end_date` null by design for current active
   registration events.
4. Document that registration rows are event-like, not slowly changing
   dimensions.

### 7. `player_registrations.registration_duration_days` - resolved in the pipeline

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Expected null behavior | Expected if treated as source field |
| Classification | Downstream derived/placeholder field |

Recommended actions:

1. Derive only if a clear business semantic exists. Possible derivation:

   ```text
   registration_duration_days =
     date_diff('day', registration_month, snapshot_end_exclusive)
   ```

2. Avoid deriving this as a source completeness metric. The source does not
   model registration duration.
3. Document whether this duration means age of the registration record, active
   player tenure, or something else.

### 8. `player_registrations.registration_status` - fixed in the pipeline

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Related source columns | `registration_source`; `players.player_status` |
| 5K export behavior | `registration_source`: 6,229 non-null / 6,229 rows |
| Expected null behavior | Expected if Silver expects a registration-specific status |
| Classification | Bronze-to-Silver assumption / non-source placeholder |

Recommended actions:

1. Do not map `registration_status` from `registration_source`; they mean
   different things.
2. If a registration status is required, derive it downstream using explicit
   rules, likely from `players.player_status` and registration date.
3. if end date is null or in the future as of the snapshot, registration status is active, otherwise it's inactive
4. Document `registration_source` as the source field that exists.


### 9. `players.preferred_side` - resolved in the pipelines - removed from silver and gold

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Related source/export field | `player_master.dominant_hand` |
| 5K export behavior | `dominant_hand`: 6,229 non-null / 6,229 rows |
| Expected null behavior | Expected; source does not capture court-side preference |
| Classification | Intentionally unavailable from source |

Recommended actions:

1. Document `preferred_side` as unavailable in the current source contract.
2. Do not infer preferred side directly from `dominant_hand` unless a domain rule
   is explicitly approved.
3. If preferred side is analytically useful, add it as a future generator
   feature with explicit distribution/configuration, not as an accidental
   transform default.
4. If Silver keeps the column, mark it as nullable placeholder.

### 10. `regions.active_flag` - resolved in the pipeline - removed from silver and gold

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Related source fields | `regions.country_code`, `region_type`, `population` |
| 5K export behavior | `regions.country_code`: 491 non-null / 491 rows |
| Expected null behavior | Expected if Silver expects source field |
| Classification | Intentionally unavailable from source |

Recommended actions:

1. Do not treat null `active_flag` as a source defect.
2. If Silver requires an active flag, derive a constant:

   ```text
   active_flag = true
   ```

   for all exported regions, because exported regions are selected as relevant
   to the release snapshot.
3. Document this as a downstream convenience flag, not source data.

### 11. `clubs.active_flag`- resolved in the pipeline - removed from silver and gold

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Related source fields | `clubs.founding_date`; no closure/dissolution date |
| Expected null behavior | Expected if Silver expects source field |
| Classification | Intentionally unavailable from source |

Recommended actions:

1. Do not treat null `clubs.active_flag` as a source defect.
2. If Silver requires an active flag, derive a constant `true` for exported
   clubs or derive from snapshot inclusion rules.
3. If future club lifecycle modeling is needed, add explicit source fields such
   as `closure_date` or `club_status`.

### 12. `clubs.country_code` - resolved in the pipelines

| Item | Finding |
|---|---|
| Source DB column | Not present directly on `clubs` |
| Exported source-file column | Not present directly on `clubs.parquet` |
| Inferable through | `clubs.region_id -> regions.id -> regions.country_code` |
| 5K export behavior | `clubs.region_id`: 2,434 non-null / 2,434 rows; `regions.country_code`: 491 non-null / 491 rows |
| 250K comparator | Current DB: 4,000 clubs; joined `regions.country_code` 100% non-null |
| Expected null behavior | Silver `clubs.country_code` should be derivable, not source-populated |
| Classification | Bronze-to-Silver transform issue if not joined through regions |

Recommended actions:

1. Populate Silver `clubs.country_code` by joining:

   ```text
   clubs.region_id = regions.id
   clubs.country_code = regions.country_code
   ```

2. Keep `clubs.parquet` source contract unchanged 
3. Add a transform test that all Silver clubs with valid `region_id` receive a
   non-null `country_code`.
4. Document that club country is region-derived.

### 13. `teams.team_name` - resolved - removed from silver and gold - not needed

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Expected null behavior | Expected |
| Classification | Intentionally unavailable from source |

Source semantics:

Teams are generated as persistent two-player identities. The source system does
not currently assign display names to generated teams.

Recommended actions:

1. Document `team_name` as unavailable from the source generator.
2. If a display name is required downstream, derive one from team id or member
   names in Silver/Gold.
3. Avoid adding a synthetic source column unless team naming is required by a
   product-facing use case.

### 14. `matches.competition_category` - resolved in the pipeline

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Related source/export field | `matches.match_type` |
| 5K export behavior | `match_type`: 70,867 non-null / 70,867 rows |
| Expected null behavior | Expected if Silver expects `competition_category` literally |
| Classification | Bronze-to-Silver naming/semantic assumption |

Source match fields:

```text
match_type
court_type
match_format
winning_team_id
total_points_played
batch_id
```

Recommended actions:

1. Decide whether Silver `competition_category` is intended to be a renamed
   `match_type`.
2. If yes, map:

   ```text
   competition_category = match_type
   ```

3. Add an audit rule that distinguishes missing source fields from intentionally
   unmapped placeholders.

### 15. `matches.match_status` -  removed from the pipelines - complete

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Expected null behavior | Expected |
| Classification | Intentionally unavailable from source |

Source semantics:

Generated matches are persisted completed match facts. The generator does not
model scheduled/cancelled/in-progress match state in the student export.

Recommended actions:

1. If Silver requires status, derive:

   ```text
   match_status = 'completed'
   ```

   for generated match rows.
2. Document this as downstream derivation, not source data.
3. Add source modeling only if future pipelines include non-completed match
   states.

### 16. `match_teams.pre_match_team_rating` - resolved in the pipelines

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Related source/export field | `match_teams.average_team_rating` |
| 5K export behavior | `average_team_rating`: 141,734 non-null / 141,734 rows |
| Expected null behavior | Expected if Silver expects exact field |
| Classification | Bronze-to-Silver semantic mismatch |

Source semantics:

`match_teams.average_team_rating` is the average rating for the two players on
that side at match time. It is the closest source equivalent to a pre-match team
rating, but the source does not name it that way.

Recommended actions:

1. Silver `pre_match_team_rating` means the average team rating at match
   time, map:

   ```text
   pre_match_team_rating = average_team_rating
   ```

2. Document the semantic as an average of player ratings, not a separately
   maintained team rating.
3. Keep original `average_team_rating` available for lineage or rename with
   explicit documentation.

### 17. `match_teams.post_match_team_rating` - resolved in pipelines

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Related source data | Player-level rating updates in `player_rating_history` |
| Expected null behavior | Expected |
| Classification | Intentionally unavailable from source |

Source semantics:

The source generator stores player-level rating history, not persistent
team-level pre/post ratings.

Recommended actions:

1. Do not expect this field from source.
2. Derive downstream by joining match participants to
   player-level rating history after the match and averaging player post-match
   ratings.
3. Document derived semantics carefully, including timing and whether rating
   rows are selected by `match_date`, `batch_id`, or rating sequence.

### 18. `match_teams.rating_change` - resolved in pipelines

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Related source data | Player-level rating deltas can be derived from `player_rating_history` |
| Expected null behavior | Expected |
| Classification | Downstream derived field |

Recommended actions:

1. Derive only if `pre_match_team_rating` and `post_match_team_rating` are
   defined:

   ```text
   rating_change = post_match_team_rating - pre_match_team_rating
   ```

2. Do not flag this as a source export issue.
3. Add derivation tests using a small known match/player-rating fixture.

### 19. `player_assessment_history.assessment_confidence` - resolved in pipelines

| Item | Finding |
|---|---|
| Source DB column | Not present under this name |
| Source DB equivalent | `player_assessment_history.confidence_score` |
| Exported source-file column | `confidence_score` |
| 5K export behavior | `confidence_score`: 289,697 non-null / 289,697 rows |
| Expected null behavior | Silver should be populated if mapped from `confidence_score` |
| Classification | Bronze-to-Silver transform naming issue |

Recommended actions:

1. Update Silver mapping:

   ```text
   assessment_confidence = confidence_score
   ```

2. Preserve source-native `confidence_score` in Bronze/raw lineage.
3. Add audit coverage that fails when `assessment_confidence` is null while
   source `confidence_score` is populated.

### 20. `player_assessment_history.assessor_source`  - removed from silver and Gold

| Item | Finding |
|---|---|
| Source DB column | Not present |
| Exported source-file column | Not present |
| Related source fields | `assessment_type`, `derived_from_matches` |
| 5K export behavior | `assessment_type`, `assessment_value`, `confidence_score`, and `derived_from_matches` are all 100% populated |
| Expected null behavior | Expected if Silver expects source field |
| Classification | Intentionally unavailable from source |

Source semantics:

Assessments are generated synthetic time-series rows. The current model records
the assessment type and whether/how many matches informed the assessment, but
not an assessor identity/source.

Recommended actions:

1. Document `assessor_source` as unavailable from source.
2. If useful, derive a constant such as `synthetic_generator` downstream, but
   mark it as derived metadata.
3. If future source-level assessor provenance matters, add an explicit source
   field to `player_assessment_history`.

## Confirmed Source-Generation Bugs

### Bug: Ad hoc team country is not populated

Impact:

- `teams.country_code` nulls are concentrated entirely in `ad_hoc` teams.
- This produces the reported 85.77% null rate in the 5K release.
- The same pattern exists in the currently populated 250K source run.

Cause:

- Competitive team generation passes `country_code`.
- Ad hoc team generation omits it.

Recommended fix:

1. Add country derivation to ad hoc pair creation.
2. Pass `country_code` into `TeamIdentityRegistry.get_or_create_team()`.
3. Add regression tests for ad hoc country population.
4. Backfill existing generated/exported artifacts where required.

## Fields Intentionally Unavailable From Source

These should be documented as unavailable, nullable placeholders, or downstream
derivations:

- `players.preferred_side`
- `regions.active_flag`
- `clubs.active_flag`
- `teams.team_name`
- `matches.match_status`
- `match_teams.post_match_team_rating`
- `match_teams.rating_change`
- `player_assessment_history.assessor_source`
- `player_registrations.effective_end_date`
- `player_registrations.registration_duration_days`
- `player_registrations.registration_status`

## Fields Available Under Different Names

These Silver nulls should be fixed in Bronze-to-Silver mapping:

| Silver field | Source/export field |
|---|---|
| `team_memberships.membership_start_date` | `team_memberships.joined_date` |
| `club_memberships.membership_end_date` | `club_memberships.end_date` |
| `player_registrations.effective_start_date` | `player_registrations.registration_month` |
| `player_assessment_history.assessment_confidence` | `player_assessment_history.confidence_score` |
| `matches.competition_category`, if intended as match category | `matches.match_type` |
| `match_teams.pre_match_team_rating`, if intended as at-match average | `match_teams.average_team_rating` |
| `clubs.country_code` | `clubs.region_id -> regions.country_code` |

## Recommended Action Plan

1. Fix the source generator bug for `teams.country_code` on ad hoc teams.
2. Update Bronze-to-Silver column mappings for renamed source fields:
   `joined_date`, `end_date`, `registration_month`, `confidence_score`,
   `match_type`, and `average_team_rating`.
3. Add downstream derivations where the column is intentionally analytical:
   membership duration, optional active flags, optional match status, optional
   team rating changes.
4. Mark intentionally unavailable fields as nullable placeholders or remove them
   from Silver if they are not required.
5. Update Silver audit rules to distinguish:
   - source-required fields;
   - renamed source fields;
   - downstream-derived fields;
   - intentionally unavailable placeholder fields.
6. Add regression tests around the NAPA 5K release shape so future raw reloads
   do not reintroduce false 100% null findings for fields that are populated
   under source-native names.
