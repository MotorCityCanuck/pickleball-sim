# NAPA Team Identity Generator Implementation Plan

## Purpose

This document updates the implementation plan for the NAPA team identity design
change based on the clarified data model decision:

- keep the current `teams.team_type` concept;
- introduce a separate team identity classification for `competitive` versus
  `ad_hoc`;
- ensure every match side resolves to a persistent `teams.id`;
- keep the generator and student-facing dataset simple enough for learning use.

The plan is intentionally scoped to data generator, schema, export, validation,
and documentation changes. It is not an implementation patch.

## Design Decision

The generator must model two independent team concepts.

| Concept | Proposed field | Meaning | Example values |
|---|---|---|---|
| Doubles composition | `team_type` | What kind of doubles roster the pair is | `mens_doubles`, `womens_doubles`, `mixed_doubles`, `open_doubles` |
| Team identity class | `team_identity_type` | Whether the pair was formed as a registered competitive team or an ad hoc casual team | `competitive`, `ad_hoc` |

`team_type` must not be repurposed. Existing tournament, configuration, and
analytics code already uses it for doubles composition, and preserving that
meaning avoids unnecessary breakage.

`team_identity_type` is the new stable classifier. It is assigned once when the
team row is created and never changes.

## Required Behavior

1. Every two-player partnership that appears in a match has exactly one
   persistent `teams.id`.
2. The same unordered player pair cannot map to multiple team IDs.
3. Every team has a fixed `team_type` describing doubles composition.
4. Every team has a fixed `team_identity_type` describing competitive/ad hoc
   identity.
5. `team_identity_type` never changes.
6. No promotion, demotion, registration lifecycle, retrospective relabeling, or
   team epochs are introduced.
7. `match_teams.source_team_id` is populated for every match side and points to
   `teams.id`.
8. Raw exported `match_teams.team_id` is populated for every match side.
9. `matches.winning_team_id` must resolve to one of the two persistent teams in
   the match.
10. Both `competitive` and `ad_hoc` teams remain valid candidates for downstream
    analytics.

## Current Repo Findings

The current codebase has the following relevant behavior:

- `Team.team_type` is currently constrained to doubles composition values in
  `backend/app/models/teams.py` and `backend/schema.sql`.
- `TeamGenerator` samples current `team_type` values using
  `team_formation.team_type_weights`.
- `competitive_team_rate` currently affects persistence probability, not a
  stored team identity classifier.
- `MatchGenerator` creates competitive sides from persisted `Team` rows and
  creates ad hoc sides as temporary `PairCandidate` objects.
- Temporary ad hoc candidates set `source_team_id=None`.
- `MatchTeam.source_team_id` is exported as raw `match_teams.team_id`.
- `matches.winning_team_id` currently stores `match_teams.id`, not persistent
  `teams.id`.
- `RatingUpdateGenerator` currently determines match wins by comparing
  `match.winning_team_id` to `match_team.id`.
- Student dataset validation currently validates
  `matches.winning_team_id -> match_teams.id`.
- Tournament simulation uses `teams.team_type` for tournament division checks,
  so that field must stay as doubles composition.

## Proposed Schema Changes

### `teams`

Add:

```sql
team_identity_type VARCHAR(30) NOT NULL
```

Allowed values:

```text
competitive
ad_hoc
```

Recommended constraint:

```sql
CONSTRAINT chk_team_identity_type
CHECK (team_identity_type IN ('competitive', 'ad_hoc'))
```

Optional but recommended:

```sql
roster_key VARCHAR(64) NOT NULL
```

Recommended unique constraint:

```sql
UNIQUE (generation_run_id, roster_key)
```

`roster_key` would be a canonical unordered player-pair key such as
`min_player_id:max_player_id`. It can remain internal and excluded from student
exports unless a later requirement says otherwise.

### `match_teams`

Keep `source_team_id` as the physical persistent team reference. It already
exists and already has a foreign key to `teams.id`.

Change the generation contract:

- `source_team_id` is required by generator behavior for all newly generated
  match-side rows.
- Exported raw `team_id` remains an alias of `source_team_id`.

Consider making `source_team_id` non-null in the physical schema after migration
if all fixtures and tests are updated. If immediate compatibility is a concern,
keep it nullable physically and enforce non-null through generation validation
first.

### `matches`

Change semantics:

- `winning_team_id` should point to persistent `teams.id`.
- It must equal one of the two `match_teams.source_team_id` values for the same
  match.

This is a semantic breaking change for downstream consumers currently joining
`matches.winning_team_id` to `match_teams.id`.

## Generator Design

### Canonical Pair Registry

Introduce a single canonical pair helper:

```python
def player_pair_key(first_player_id: int, second_player_id: int) -> tuple[int, int]:
    return tuple(sorted((int(first_player_id), int(second_player_id))))
```

Create a registry for a generation run:

- loads existing teams and active memberships;
- maps canonical player pair to `team_id`;
- records `team_type` and `team_identity_type`;
- prevents duplicate team creation for the same unordered pair;
- creates a persistent team and two membership rows when a new ad hoc pair is
  needed.

The registry should be used by both team formation and match generation.

### Team Generation

Update `TeamGenerator` so it assigns both dimensions:

- `team_type`: current composition value sampled from
  `team_formation.team_type_weights`;
- `team_identity_type`: sampled as `competitive` or `ad_hoc` using a new or
  clarified configuration value.

Recommended config cleanup:

- Keep `team_formation.team_type_weights` for composition.
- Rename or reinterpret `competitive_team_rate` as the probability that a newly
  formed persistent team is `competitive`.
- Preserve existing persistence probability config, but apply it based on
  `team_identity_type`.

Example:

```python
identity_type = (
    "competitive"
    if rng.random() < config.competitive_team_rate
    else "ad_hoc"
)
persistence_probability = (
    config.team_persistence_probability_competitive
    if identity_type == "competitive"
    else config.team_persistence_probability_recreational
)
```

The team generator should register every created team pair in the canonical
registry. It must not create a second team for a player pair that already exists
in the generation run.

### Match Generation

Update `MatchGenerator` so both current match sources resolve to persisted teams:

- Existing persisted team candidates become normal team candidates with
  `source_team_id=team.id`.
- `pairing_source` should be derived from `Team.team_identity_type`.
- Temporary ad hoc candidate creation should be replaced by registry-backed team
  resolution.

For a sampled ad hoc pair:

1. derive the canonical pair key;
2. ask the registry for an existing team;
3. if absent, create `Team(team_identity_type='ad_hoc', team_type=<composition>)`;
4. create two `TeamMembership` rows;
5. return a `PairCandidate` with `source_team_id` populated.

Ad hoc teams created during match generation should have:

- `team_identity_type='ad_hoc'`;
- `team_type` derived from the two players;
- `formation_date` equal to the first match date or batch month;
- `team_status='active'`;
- appropriate country/region attribution using existing rules where possible;
- chemistry and persistence values generated consistently with existing team
  logic.

### Pairing Source Naming

Current `match_teams.pairing_source` values are:

- `competitive_team`
- `ad_hoc`

Options:

1. Keep these values for backward compatibility and set them from
   `team_identity_type`.
2. Simplify to `competitive` and `ad_hoc`, which aligns with the new team
   identity column but requires more downstream updates.

Recommended minimal change: keep `competitive_team` and `ad_hoc` in
`match_teams.pairing_source`, but document that it is derived from the persistent
team identity class.

### Winner Semantics

Update match winner assignment:

Current behavior:

```python
match.winning_team_id = winning_match_team.id
```

Target behavior:

```python
match.winning_team_id = winning_match_team.source_team_id
```

Validation must prove that `matches.winning_team_id` is one of the two
`match_teams.source_team_id` values for that same match.

`RatingUpdateGenerator` must update match-win logic accordingly:

```python
match_won = 1 if match.winning_team_id == match_team.source_team_id else 0
```

## Export and Validation Changes

### Raw Student Dataset Export

Update `teams.parquet` to include the new identity column:

```text
id
team_type
team_identity_type
team_status
country_code
formation_date
dissolution_date
```

Keep `match_teams.parquet` field name `team_id`, sourced from
`MatchTeam.source_team_id`.

Expected contract after change:

- `match_teams.team_id` is non-null.
- `match_teams.team_id -> teams.id`.
- `matches.winning_team_id -> teams.id`.
- `matches.winning_team_id` must be one of the participating
  `match_teams.team_id` values.

### Validation Updates

Update `backend/app/exports/student_dataset/validation.py` and
`scripts/student_dataset_duckdb_quality_check.sql`.

Required validations:

- every `match_teams.team_id` resolves to `teams.id`;
- no null `match_teams.team_id`;
- every match has exactly two match teams;
- no match uses the same `team_id` on both sides;
- no player appears on both sides of a match;
- `matches.winning_team_id` resolves to a participating persistent team;
- each team has exactly two active membership rows for the relevant period;
- no unordered player pair maps to multiple `team_id` values.

## Testing Plan

### Unit Tests

Add or update tests for:

- canonical pair key treats `(A, B)` and `(B, A)` as the same pair;
- team registry reuses an existing team for the same pair;
- team registry prevents duplicate teams for one unordered pair;
- `TeamGenerator` assigns `team_type` and `team_identity_type` independently;
- `TeamGenerator` never changes `team_identity_type` during lifecycle updates;
- ad hoc match sampling creates persistent ad hoc teams;
- repeated ad hoc pair appearances reuse the same `team_id`;
- `MatchTeam.source_team_id` is always populated;
- match-team players match persistent team memberships;
- `matches.winning_team_id` stores persistent `teams.id`;
- `RatingUpdateGenerator` still computes wins correctly with new winner
  semantics.

### Export Tests

Update student dataset writer/query tests to prove:

- `teams.parquet` includes `team_identity_type`;
- `match_teams.team_id` is non-null for competitive and ad hoc teams;
- `matches.winning_team_id` joins to `teams.id`;
- `matches.winning_team_id` is one of the two participating match-side team IDs;
- raw output no longer requires downstream reconstruction to identify ad hoc
  partnerships.

### Regression Tests

Run targeted tests:

```bash
.venv/bin/pytest backend/tests/test_team_generator.py
.venv/bin/pytest backend/tests/test_match_generator.py
.venv/bin/pytest backend/tests/test_rating_update_generator.py
.venv/bin/pytest backend/tests/test_student_dataset_queries.py
.venv/bin/pytest backend/tests/test_student_dataset_writer.py
.venv/bin/pytest backend/tests/test_orm_consistency.py
```

Then run broader pipeline/audit tests:

```bash
.venv/bin/pytest backend/tests/test_monthly_pipeline.py
.venv/bin/pytest backend/tests/test_realism_audit.py
.venv/bin/pytest backend/tests/test_student_dataset_service.py
```

## Documentation Updates

Update:

- `docs/development/napa_team_identity_data_generator_design_change.md`
- `docs/development/student_facing_dataset_data_dictionary.md`
- `docs/gold_source_contract.md`
- `docs/development/napa_parquet_inventory.md`
- `docs/generation_logic/configuration_parameters_specification.md`
- `docs/architecture/configuration_payload_architecture.md`

Documentation must clearly distinguish:

- `team_type`: doubles composition;
- `team_identity_type`: competitive/ad hoc classification;
- `match_teams.id`: match-side row ID;
- `match_teams.team_id`: persistent team ID;
- `matches.winning_team_id`: persistent winning team ID.

## Suggested Implementation Order

1. Add schema/model fields and constraints.
2. Add canonical pair helper and registry.
3. Update `TeamGenerator` to populate `team_identity_type` and prevent duplicate
   player pairs.
4. Update `MatchGenerator` to persist/reuse ad hoc teams and populate
   `source_team_id` for all sides.
5. Update `matches.winning_team_id` semantics and dependent rating logic.
6. Update export projection and validation.
7. Update tests.
8. Update docs and quality-check SQL.
9. Run targeted tests, then pipeline/audit tests.
10. Regenerate raw parquet datasets after code validation.

## Risks and Decisions To Confirm

1. **Column name:** this plan uses `team_identity_type`; alternatives are
   `team_class`, `team_source_type`, or `team_formality`.
2. **Physical non-null constraint:** make `match_teams.source_team_id` non-null
   immediately or enforce through generator validation first.
3. **Roster key persistence:** storing `roster_key` simplifies validation and
   duplicate prevention but exposes another internal identity mechanism in the
   database.
4. **Winner semantic break:** downstream pipelines must be coordinated because
   `matches.winning_team_id` changes from `match_teams.id` to `teams.id`.
5. **Config naming:** `competitive_team_rate` can remain but should be
   documented as identity-class probability rather than persistence shorthand.

