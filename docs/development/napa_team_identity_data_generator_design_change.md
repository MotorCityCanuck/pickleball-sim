# NAPA Team Identity Model — Data Generator Design Change and Implementation Plan

## Purpose

This document defines the approved design change for team identity in the NAPA synthetic pickleball data generator. It is intended to be used as an implementation specification for Codex.

The change is designed to eliminate ambiguity between ad hoc partnerships and competitive teams while preserving the instructional focus of the case study: enterprise-style data engineering, pipeline development, data quality, analytics, governance, and decision support.

The implementation must favor a simple, stable, and explainable data model over realistic but unnecessary lifecycle complexity.

---

## 1. Approved Design Decision

Each unique combination of two players shall have exactly one persistent `team_id` and one fixed `team_type`.

Allowed `team_type` values:

- `ad_hoc`
- `competitive`

The following rules are mandatory:

1. Every two-player partnership that participates in a match receives a persistent `team_id`.
2. The same unordered combination of two players may not exist under more than one `team_id`.
3. A team is assigned either `ad_hoc` or `competitive` when it is generated.
4. `team_type` never changes.
5. Ad hoc teams remain ad hoc for the full life of the generated dataset.
6. Competitive teams remain competitive for the full life of the generated dataset.
7. No promotion, registration, reclassification, or team-type lifecycle logic shall be introduced.
8. No separate `registration_status`, `registration_date`, promotion date, or equivalent concept shall be added.
9. Every match side must resolve to a valid persistent `team_id`.
10. Both ad hoc and competitive teams remain analytically eligible for Olympic consideration.

---

## 2. Business Definitions

### 2.1 Competitive Team

A competitive team is a formally established NAPA competitive partnership. It is generated as a durable team and remains classified as `competitive` throughout the dataset.

Competitive teams will generally have stronger partnership continuity, greater match history, and higher confidence in partnership-level analytics, but these characteristics should emerge from the generated data rather than from automatic scoring bonuses.

### 2.2 Ad Hoc Team

An ad hoc team is an occasional or casually formed partnership. It receives a persistent `team_id` for identity consistency, but remains classified as `ad_hoc` throughout the dataset.

Ad hoc teams may participate in one or more matches. They may be high quality and may be considered in downstream Olympic selection analytics. Their likely disadvantage should come from limited partnership evidence, lower continuity, or lower confidence—not from an arbitrary hard exclusion.

---

## 3. Non-Goals

The implementation must not introduce any of the following:

- promotion from ad hoc to competitive;
- demotion from competitive to ad hoc;
- registration-state history;
- retrospective relabeling of prior matches;
- multiple team records for the same pair;
- team epochs for the same pair;
- student-facing partnership reconstruction logic;
- match-level team identity that is separate from persistent team identity;
- hard exclusion of ad hoc teams from downstream analysis.

These concepts are intentionally excluded because they add complexity without supporting the desired teaching outcomes.

---

## 4. Canonical Team Identity Rule

The generator must treat a player pair as unordered for identity purposes.

For players `player_a_id` and `player_b_id`, derive a canonical pair key internally:

```text
pair_key = min(player_a_id, player_b_id) + '|' + max(player_a_id, player_b_id)
```

The exact implementation may use a tuple, hash, normalized string, or database key, but it must guarantee that:

```text
(A, B) == (B, A)
```

The canonical pair key is primarily an internal generator and validation mechanism. It does not need to be exported unless the current architecture benefits from doing so and the change is explicitly justified.

---

## 5. Target Data Model Behavior

### 5.1 `teams`

The `teams` entity remains the persistent source of team identity.

Minimum expected semantics:

| Field | Required meaning |
|---|---|
| `id` or `team_id` | Persistent identifier for one unique two-player combination |
| `team_type` | Fixed value: `ad_hoc` or `competitive` |
| `team_status` | Operational state such as active, inactive, or dissolved, if already supported |
| `country_code` | Team country attribution according to existing generator rules |
| `formation_date` | Initial formation or first recognized participation date |
| `dissolution_date` | Optional end date if the current model supports team inactivity or dissolution |

Do not add registration-specific fields.

### 5.2 `team_memberships`

`team_memberships` must resolve each persistent team to exactly two players for the relevant active period.

Required behavior:

- each generated team has two valid member records;
- the same player pair cannot map to multiple team IDs;
- player order or position must not affect team identity;
- membership records must remain consistent with the team’s match participation.

### 5.3 `match_teams`

Each match-side record must reference the persistent `team_id` that identifies the two players on that side.

Required behavior:

- every match has exactly two match-side records;
- every match-side record resolves to a valid team;
- both ad hoc and competitive teams use the same relationship path;
- there are no valid match-side records with a missing `team_id`;
- match-side player membership must agree with the persistent team membership.

If the current physical schema does not contain `team_id` on `match_teams`, Codex must inspect the existing model and implement the smallest safe schema change that creates an explicit, reliable relationship between each match side and the persistent team entity.

### 5.4 `matches.winning_team_id`

The winning team identifier must resolve to one of the two persistent teams that participated in the match.

This must be validated after generation.

---

## 6. Team Generation Strategy

Codex must inspect the current generator before changing behavior. Preserve the existing scale, bias, regional, player lifecycle, match generation, rating, and hidden simulation logic unless a change is strictly required to implement this specification.

Recommended generation flow:

1. Generate or load the eligible player population.
2. Generate the competitive team population using existing competitive-team logic.
3. Register each competitive pair in a canonical pair lookup.
4. Generate ad hoc pairings only from player combinations not already assigned to an existing team.
5. For every new ad hoc combination:
   - create one persistent team record;
   - assign `team_type = 'ad_hoc'`;
   - create the corresponding two membership records;
   - add the pair to the canonical pair lookup.
6. Reuse the same `team_id` whenever that pair appears again.
7. Never generate a second team record for the same pair.
8. Never change `team_type` based on match count, duration, performance, or recurrence.
9. Generate match-side records using the already resolved persistent `team_id`.

---

## 7. Match Frequency and Team-Type Behavior

Team type may influence generation probabilities, but not identity rules.

The generator may continue to produce realistic differences such as:

- competitive teams playing more frequently;
- competitive teams appearing across more months or tournaments;
- ad hoc teams appearing less frequently;
- ad hoc teams having shorter active spans;
- competitive teams having more stable partnership-level hidden factors.

However:

- these are generation characteristics, not promotion criteria;
- no threshold converts one team type into another;
- an ad hoc team may appear more than once;
- a competitive team may have limited activity;
- team type must not be inferred downstream solely from match count.

---

## 8. Data Quality Requirements

The generator must enforce or validate the following rules before export.

### 8.1 Identity Rules

- one unique `team_id` per unordered player pair;
- no duplicate pair under multiple IDs;
- no single team ID associated with different player pairs;
- valid `team_type` on every team;
- no team-type transitions.

### 8.2 Membership Rules

- exactly two players per team for the active period;
- all membership player IDs resolve to valid players;
- all membership team IDs resolve to valid teams;
- no duplicate active membership rows for the same team/player combination.

### 8.3 Match Rules

- exactly two match-side records per match;
- every match side resolves to a valid persistent team;
- players listed on a match side match the persistent team membership;
- the winning team resolves to one of the two participating teams;
- no match contains the same team on both sides;
- no player appears on both sides of the same match.

### 8.4 Cross-Release Rules

The 5K, 50K, and 250K datasets must use the same schema and behavioral rules. Scaling must be configuration-driven.

---

## 9. Export and Schema Compatibility

Codex must minimize schema disruption.

Implementation guidance:

1. Preserve existing field names where practical.
2. Reuse the existing `team_type` field if present.
3. Do not add `registration_status` or registration-related fields.
4. Add a match-side `team_id` only if the current schema lacks an explicit persistent team reference.
5. Update schema definitions, manifest metadata, export specifications, and sample-data documentation only where required.
6. Preserve source file names unless a change is technically unavoidable.
7. Ensure all generated Parquet files remain readable by the current pipeline after coordinated pipeline changes.

---

## 10. Implementation Plan for Codex

### Phase 1 — Discovery

1. Identify all generator modules that create:
   - teams;
   - team memberships;
   - ad hoc pairings;
   - competitive teams;
   - match sides;
   - match-side players;
   - winning team IDs;
   - exported Parquet schemas.
2. Identify all uses of nullable or optional team identity.
3. Identify any existing logic that reconstructs pairs from players.
4. Identify any existing team promotion, reuse, or duplicate-pair behavior.
5. Produce a concise impact summary before editing.

### Phase 2 — Canonical Pair Registry

1. Implement a single canonical pair-key function.
2. Create or refactor a team registry keyed by the canonical pair.
3. Ensure the registry returns the same `team_id` for the same unordered pair.
4. Prevent duplicate team creation.
5. Preserve deterministic generation under existing seeds.

### Phase 3 — Team Creation Refactor

1. Refactor competitive-team generation to register all created pairs.
2. Refactor ad hoc-team generation to:
   - reject pairs already used by any team;
   - create a persistent team record once;
   - reuse that team on future appearances.
3. Assign fixed `team_type` at creation.
4. Remove or disable any promotion or reclassification logic.
5. Do not introduce registration-state fields.

### Phase 4 — Match Generation Refactor

1. Resolve both match sides through the persistent team registry.
2. Populate the match-side team reference consistently.
3. Ensure match-team-player rows match persistent team membership.
4. Ensure winner references use the persistent team identity.
5. Eliminate valid match records with missing team identity.

### Phase 5 — Validation and Testing

Add or update automated tests covering:

- canonical pair ordering;
- duplicate-pair prevention;
- persistent ID reuse;
- fixed team type;
- exact two-player membership;
- two sides per match;
- valid winner participation;
- no self-match;
- no player on both sides;
- consistent output across repeated runs with the same seed;
- 5K, 50K, and 250K configuration compatibility.

### Phase 6 — Documentation and Migration Notes

Update:

- generator README;
- schema documentation;
- data dictionary;
- dataset manifest specification;
- change log;
- any architecture or design notes that describe team identity.

Document the change as a breaking semantic correction if existing generated datasets used nullable or non-persistent team identity.

---

## 11. Acceptance Criteria

The implementation is complete only when all of the following are true:

1. Every match side has a valid persistent team reference.
2. Every unique unordered player pair maps to exactly one `team_id`.
3. No player pair exists as both ad hoc and competitive.
4. No team changes type.
5. No registration-status concept is introduced.
6. Ad hoc teams can appear in one or multiple matches.
7. Competitive and ad hoc teams share the same schema and join path.
8. Winner references resolve to a participating team.
9. Existing hidden bias and simulation logic remains unchanged except where necessary.
10. All automated tests pass.
11. The generator successfully produces the 5K dataset.
12. A sampled 50K run validates scaling behavior.
13. The full 250K run is supported by the same configuration-driven logic.
14. Updated documentation clearly explains the fixed team-type model.

---

## 12. Required Codex Deliverables

Codex should provide:

1. a change-impact summary;
2. the code changes;
3. new and updated automated tests;
4. schema and documentation updates;
5. a migration note describing incompatibility with prior generated releases, if applicable;
6. validation results for at least the 5K dataset;
7. a list of any assumptions or unresolved issues;
8. confirmation that no promotion or registration-state logic was introduced.

---

## 13. Implementation Guardrails

- Do not redesign unrelated generator components.
- Do not expose hidden simulation factors.
- Do not modify rating, fatigue, affinity, regional bias, or data-quality injection logic unless required by this change.
- Do not hard-code scale-specific behavior.
- Do not create different schemas for 5K, 50K, and 250K releases.
- Do not silently preserve duplicate pair identities for backward compatibility.
- Prefer clear validation failures over ambiguous repair logic.
- Keep the implementation understandable and maintainable for instructor support.

---

## 14. Final Design Summary

The approved model is intentionally simple:

```text
One unordered player pair
        -> one persistent team_id
        -> one fixed team_type
        -> zero or more matches
```

`team_type` is contextual information, not a lifecycle state.

Ad hoc teams remain ad hoc. Competitive teams remain competitive. Both may be analyzed and considered for Olympic selection. The strength and confidence of the partnership should emerge from downstream analytics rather than from generator-side eligibility rules.
