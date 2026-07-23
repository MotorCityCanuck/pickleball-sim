# NAPA Team Identity Generator Implementation Plan

## Purpose

This document captures the implementation plan for the NAPA team identity design
change after the clarified modeling decision:

- `team_type` identifies whether a team is `competitive` or `ad_hoc`;
- `team_division` identifies gender composition / competition category;
- every match side resolves to one persistent `teams.id`;
- every unordered two-player pair maps to at most one team record.

The plan is intentionally scoped to generator, schema, export, validation, and
documentation changes.

## Design Decision

The generator must model two independent team concepts.

| Concept | Field | Meaning | Values |
|---|---|---|---|
| Team identity class | `team_type` | Whether the pair was formed as a registered competitive team or an ad hoc casual team | `competitive`, `ad_hoc` |
| Doubles division | `team_division` | Gender composition / competition category | `mens_doubles`, `womens_doubles`, `mixed_doubles`, `open_doubles` |

`team_type` is immutable after creation. `team_division` preserves the current
composition meaning that older code stored in `team_type`.

## Required Behavior

1. Every two-player partnership that appears in a match has exactly one
   persistent `teams.id`.
2. The same unordered player pair cannot map to multiple team IDs.
3. Competitive teams are created with `team_type = 'competitive'`.
4. Ad hoc teams are created with `team_type = 'ad_hoc'`.
5. Every team has one `team_division`.
6. `team_type` never changes because of match frequency, performance,
   recurrence, or lifecycle status.
7. `match_teams.source_team_id` is populated for every match side and points to
   `teams.id`.
8. Raw exported `match_teams.team_id` is populated for every match side.
9. `matches.winning_team_id` must resolve to one of the two persistent teams in
   the match after the winner-semantics step is implemented.
10. Both competitive and ad hoc teams remain valid candidates for downstream
    analytics.

## Current Repo Findings

- Older code used `teams.team_type` for division values such as
  `mixed_doubles`.
- Step 1 previously added `team_identity_type`; this plan supersedes that by
  moving identity classification into `team_type` and adding `team_division`.
- Step 2 added a canonical pair registry used by team formation and ad hoc match
  planning.
- `TeamGenerator` uses structured pairing logic based on gender, region, club,
  rating, and compatibility.
- `MatchGenerator` samples ad hoc player pairs when match configuration selects
  ad hoc pairing.
- `MatchTeam.source_team_id` is exported as raw `match_teams.team_id`.
- `matches.winning_team_id` currently stores `match_teams.id`; a later step will
  change it to persistent `teams.id`.

## Schema Direction

### `teams`

Use:

```sql
team_type VARCHAR(30) NOT NULL
team_division VARCHAR(50) NOT NULL
```

Allowed `team_type` values:

```text
competitive
ad_hoc
```

Allowed `team_division` values:

```text
mens_doubles
womens_doubles
mixed_doubles
open_doubles
```

Recommended constraints:

```sql
CONSTRAINT chk_team_type
CHECK (team_type IN ('competitive', 'ad_hoc'))

CONSTRAINT chk_team_division
CHECK (team_division IN ('mens_doubles', 'womens_doubles', 'mixed_doubles', 'open_doubles'))
```

`team_identity_type` should be removed from the target model once `team_type`
holds identity class.

### `match_teams`

Keep `source_team_id` as the physical persistent team reference. Exported raw
`team_id` remains an alias of `source_team_id`.

### `matches`

The later winner-semantics step must change `winning_team_id` from
`match_teams.id` to persistent `teams.id`.

## Team Generation Update

- The data generation process must create both competitive and ad hoc teams.
- Update the existing `TeamGenerator` so that its structured pairing logic
  creates competitive teams rather than using team type to represent gender
  composition.
- Store gender composition or competition category in `team_division`, such as:
  `mens_doubles`, `womens_doubles`, and `mixed_doubles`.
- Preserve the current gender, region, club, rating, and compatibility pairing
  logic used to create competitive teams unless changes are required to support
  the revised identity model.
- Ad hoc teams must be created when the match-generation process selects a
  casual player pairing that does not already exist in the canonical team-pair
  registry.

When a new ad hoc pairing is encountered:

1. Generate one persistent `team_id`.
2. Create one `teams` record with `team_type = 'ad_hoc'`.
3. Assign the appropriate `team_division`.
4. Create exactly two corresponding `team_memberships` records.
5. Add the unordered player pair to the canonical pair registry.
6. Reuse that same `team_id` if the pairing appears in future matches.

Competitive teams must be created with `team_type = 'competitive'`.

Ad hoc teams must be created with `team_type = 'ad_hoc'`.

A team's `team_type` is immutable:

- ad hoc teams never become competitive;
- competitive teams never become ad hoc;
- match frequency, duration, performance, or recurrence must not change
  `team_type`.

Keep lifecycle status behavior if desired, but lifecycle status must remain
separate from `team_type`.

Before creating any team, compute the canonical unordered player-pair key and
confirm that the pair does not already exist.

Do not create a competitive team if the same player pair already exists as an ad
hoc team.

Do not create an ad hoc team if the same player pair already exists as a
competitive team.

Do not create more than one team record for the same unordered player pair.

## Match Generation Update

- Competitive-team scheduling should load only persisted teams where
  `team_type = 'competitive'`.
- Ad hoc teams are reused through the canonical pair registry during casual
  player-pair planning, not through the competitive-team monthly target pool.
- `pairing_source` can remain `competitive_team`/`ad_hoc` for backward
  compatibility, but it should be derived from `teams.team_type`.
- Ad hoc sampled pairs must resolve through the canonical registry.
- If a pair already exists, reuse the existing team even if the current match
  branch selected ad hoc.
- If a pair does not exist, create an ad hoc team with the derived
  `team_division`.

## Export and Validation Changes

`teams.parquet` should include:

```text
id
team_type
team_division
team_status
country_code
formation_date
dissolution_date
```

Expected post-change contract:

- `teams.team_type` is `competitive` or `ad_hoc`.
- `teams.team_division` is the doubles composition.
- `match_teams.team_id` is non-null.
- `match_teams.team_id -> teams.id`.
- `matches.winning_team_id -> teams.id` after the winner-semantics step.
- `matches.winning_team_id` must be one of the participating match-side team IDs
  after the winner-semantics step.

## Testing Plan

Add or update tests for:

- `TeamGenerator` creates competitive teams with `team_type = 'competitive'`.
- `TeamGenerator` stores division in `team_division`.
- Existing gender/division constraints still work through `team_division`.
- Ad hoc match sampling creates persistent teams with `team_type = 'ad_hoc'`.
- Ad hoc match sampling sets the appropriate `team_division`.
- Existing pairs are reused regardless of current branch.
- A pair cannot exist as both competitive and ad hoc.
- `team_type` does not change during lifecycle updates.
- `match_teams.source_team_id` is populated for ad hoc and competitive sides.

Regression suites:

```bash
.venv/bin/pytest backend/tests/test_team_generator.py
.venv/bin/pytest backend/tests/test_match_generator.py
.venv/bin/pytest backend/tests/test_rating_update_generator.py
.venv/bin/pytest backend/tests/test_student_dataset_queries.py
.venv/bin/pytest backend/tests/test_student_dataset_writer.py
.venv/bin/pytest backend/tests/test_orm_consistency.py
```

## Documentation Updates

Update downstream docs to distinguish:

- `teams.team_type`: competitive/ad hoc identity;
- `teams.team_division`: doubles composition;
- `match_teams.id`: match-side row ID;
- `match_teams.team_id`: persistent team ID;
- `matches.winning_team_id`: persistent winning team ID after the
  winner-semantics step.

## Suggested Implementation Order

1. Update schema/model fields and constraints for `team_type` and
   `team_division`.
2. Update the canonical registry to store `team_type` and `team_division`.
3. Update `TeamGenerator` structured teams to create competitive teams.
4. Update `MatchGenerator` ad hoc creation to create ad hoc teams.
5. Update active team loading, tournament loading, exports, and tests to use
   `team_division` where division is needed.
6. Run targeted and regression tests.
