# NAPA 250K Dataset-to-Simulator Reconciliation Requirements

## 1. Purpose

Build a reusable reconciliation utility that verifies that the **released NAPA 250K Parquet dataset** is aligned with the **authoritative tournament simulator database** on the instructor classroom laptop.

The objective is to confirm that the student-facing source data and the simulator's source database represent the same generated population and competitive history before the 250K dataset is released and whenever the instructor wishes to revalidate the environment later.

This reconciliation is an **instructor data-release certification control**. It is not a student-facing data-quality process.

## 2. Critical Design Principle

The reconciliation must compare the **original released Parquet source files** directly with the **simulator database source tables**.

Do **not** compare the simulator database to student Bronze, Silver, Gold, curated, filtered, or corrected outputs.

Students may legitimately remove, quarantine, correct, or exclude records later in their pipelines because the dataset intentionally contains injected data-quality issues. Those downstream differences are expected and must not be interpreted as simulator misalignment.

For release certification, the baseline expectation is:

> **The 250K Parquet source dataset and the corresponding simulator database records must be equivalent at the source-data level.**

Where a Parquet file represents the same logical entity as a database table, the reconciliation should normally expect the same record population and equivalent values for all shared source fields, subject only to explicitly documented technical normalization such as null representation, timestamp formatting, or numeric precision.

## 3. Business Context

The NAPA assignment requires students to select valid pre-existing doubles teams from the provided dataset for the final tournament. Candidate teams must exist in the provided team records, and team membership must resolve through the team membership and player data.

The simulator therefore must recognize the same team IDs, players, team composition, country/category assignments, and relevant competition history contained in the released 250K source dataset.

This utility should provide confidence that a team selected by a student from the original 250K source files can be submitted to the instructor-managed simulator without failure caused by drift between the released dataset and the simulator database.

## 4. Scope

### 4.1 Required 250K Parquet files

At minimum, reconcile all source Parquet files included in the 250K release:

- `regions.parquet`
- `clubs.parquet`
- `club_memberships.parquet`
- `player_master.parquet`
- `player_registrations.parquet`
- `player_assessment_history.parquet`
- `teams.parquet`
- `team_memberships.parquet`
- `matches.parquet`
- `match_teams.parquet`
- `match_team_players.parquet`
- `match_games.parquet`
- `monthly_batches.parquet`

If the database contains additional simulator-only or operational tables, those tables do not need to match Parquet files unless they are explicitly mapped in configuration.

### 4.2 Tournament-critical entities

The following entities are especially important and should receive additional validation and prominent reporting:

- Players
- Teams
- Team memberships
- Matches
- Match teams
- Match team players
- Match games

### 4.3 Out of scope

The reconciliation does **not** validate:

- Student Bronze tables
- Student Silver tables
- Student Gold tables
- Student remediation logic
- Student-selected subsets after data-quality filtering
- Student rankings or team-selection methodology
- Tournament simulation probabilities or Monte Carlo correctness
- Whether injected data-quality defects are analytically appropriate

## 5. Source-of-Truth Model

For this utility, neither side should be silently treated as correct when a mismatch occurs.

The utility compares two release artifacts:

1. The 250K Parquet source release intended for students.
2. The simulator database generated from the corresponding source population.

A mismatch means the release pair is not certified until the difference is understood and either corrected or explicitly approved by the instructor.

The reconciliation output must clearly identify which side contains each differing record or value.

## 6. Configuration Requirements

The utility must be reusable and configuration-driven.

Do not hard-code instructor-specific paths, database names, passwords, hosts, ports, schemas, or table names in reconciliation logic.

Provide a configuration mechanism, preferably YAML, TOML, or environment variables plus a sample configuration file.

Suggested configuration structure:

```yaml
release_name: napa_250k
parquet_root: /path/to/napa_250k

database:
  type: postgresql
  host: localhost
  port: 5432
  database: <database_name>
  schema: <schema_name>
  user: <user>
  password_env_var: NAPA_DB_PASSWORD

output_directory: ./reconciliation_output

mappings:
  regions.parquet: regions
  clubs.parquet: clubs
  club_memberships.parquet: club_memberships
  player_master.parquet: players
  player_registrations.parquet: player_registrations
  player_assessment_history.parquet: player_assessment_history
  teams.parquet: teams
  team_memberships.parquet: team_memberships
  matches.parquet: matches
  match_teams.parquet: match_teams
  match_team_players.parquet: match_team_players
  match_games.parquet: match_games
  monthly_batches.parquet: monthly_batches
```

Actual database table names must be discovered from the existing application/database and reflected in configuration rather than assumed.

## 7. Reconciliation Levels

The implementation should perform multiple levels of validation so that failures are easy to diagnose.

### 7.1 File/table presence validation

For every configured source mapping:

- Confirm the Parquet file exists.
- Confirm the target database table exists.
- Report missing files or tables as failures.

### 7.2 Schema comparison

For each mapped entity:

- Identify the Parquet columns.
- Identify the database columns.
- Identify the configured primary/business key.
- Determine the shared source columns that should be compared.
- Report source columns missing from the database.
- Report unexpected database columns separately; simulator-only technical columns are allowed if they are not mapped as source fields.
- Compare compatible data types where useful.

The implementation must support explicit column mappings if Parquet and database names differ.

### 7.3 Record-count comparison

For every mapped entity:

- Count Parquet records.
- Count database records in the corresponding release scope.
- Report the difference.

Expected result for mapped source entities:

```text
parquet_count == database_count
```

A count mismatch is a release-certification failure unless explicitly waived.

### 7.4 Primary-key reconciliation

For every mapped entity with a stable key:

- Confirm key uniqueness in Parquet.
- Confirm key uniqueness in the database where appropriate.
- Identify keys present only in Parquet.
- Identify keys present only in the database.

Expected result:

```text
Parquet key set == Database key set
```

Do not use subset logic for the original source reconciliation. Equality is the normal release expectation.

### 7.5 Row-level value reconciliation

For records sharing the same key, compare all configured source fields.

Report:

- Key
- Column name
- Parquet value
- Database value
- Normalized values if normalization was applied

The implementation should avoid generating an unmanageably large console dump. Full mismatch details should be written to machine-readable output files.

### 7.6 Duplicate validation

Detect duplicate primary/business keys in both sources.

Important: a duplicate may itself be an intentionally injected data-quality issue. The purpose here is **not to declare the duplicate invalid**. Instead, verify that the same source-level duplicate condition is represented consistently on both sides where the database model permits it.

If the database transformation or key design makes literal duplicate comparison impossible, document that entity's reconciliation strategy explicitly rather than silently dropping the check.

## 8. Technical Normalization Rules

The utility may normalize values only to eliminate technical representation differences, not business differences.

Allow configurable normalization for cases such as:

- `NULL` vs Parquet null
- Date vs timestamp representation
- Time zone normalization where source meaning is unchanged
- Decimal scale/precision
- Floating-point comparison tolerance
- Boolean representation
- Trailing whitespace only if known to be introduced by storage mechanics rather than source generation

Do **not** normalize away meaningful differences such as:

- Different IDs
- Different country codes
- Different team categories
- Different player assignments
- Different scores
- Different ratings
- Different match winners
- Different dates
- Different statuses

Any normalization rules must be documented in the final report.

## 9. Tournament-Specific Integrity Checks

In addition to general source equality, perform a dedicated tournament compatibility section.

### 9.1 Team existence

Every `teams.parquet` team ID must exist in the corresponding database team table.

Expected:

```text
missing_team_ids = 0
extra_team_ids = 0
```

### 9.2 Team membership equivalence

For every team ID, compare the complete set of player memberships between Parquet and the database.

Expected:

```text
Parquet membership set == Database membership set
```

The check must detect:

- Missing member
- Extra member
- Member attached to wrong team
- Player-position mismatch if position is part of the source model
- Membership date mismatch if relevant to source equivalence

### 9.3 Player existence

Every player referenced by `team_memberships.parquet` must resolve to the same player ID in both the Parquet release and simulator database.

### 9.4 Country equivalence

For every team, compare the source country assignment between Parquet and database.

### 9.5 Team category/type equivalence

For every team, compare the source team type/category used to distinguish men's doubles, women's doubles, and mixed doubles.

### 9.6 Competition-history equivalence

Where the simulator uses historical match/game records to initialize ratings, skill, chemistry, fatigue, or other simulation inputs, verify that the associated source records are also aligned between Parquet and database.

At minimum verify the equality of relevant IDs and relationships across:

```text
teams
  -> match_teams
  -> matches
  -> match_games

players
  -> match_team_players
  -> match_teams
  -> matches
```

## 10. Injected Data-Quality Issue Handling

This requirement is critical.

The NAPA 250K source dataset intentionally contains data-quality issues. Those defects may include records that students later reject, quarantine, repair, standardize, or exclude.

The reconciliation must therefore distinguish between:

### Source equivalence

Whether the Parquet release and simulator database contain the same underlying source data.

### Analytical usability

Whether a student should use a particular record after applying data-quality rules.

This tool addresses **source equivalence only**.

Therefore:

- Do not remove suspicious records before reconciliation.
- Do not apply student-style data-cleaning rules before comparison.
- Do not require every team to survive a hypothetical Silver-layer data-quality process.
- Do not treat an intentionally defective record as a reconciliation failure if the same defect is present on both sides.
- Do treat it as a reconciliation failure if the defect exists in Parquet but the corresponding database record differs, is absent, or has been silently corrected without an explicitly approved design reason.

## 11. Release Identification / Drift Prevention

The utility should make it difficult to accidentally compare the wrong release.

Capture and report:

- Reconciliation run timestamp
- Release name
- Parquet root path
- Database host/database/schema identifiers, excluding passwords
- Git commit hash of the reconciliation code if available
- Application/simulator Git commit hash if obtainable
- Parquet file sizes
- Parquet row counts
- Optional cryptographic hash per Parquet file

Recommended: calculate SHA-256 hashes for each released Parquet file and include them in the report. This creates a release fingerprint that can be retained with the certified student dataset.

## 12. Performance Requirements

The reconciliation must be practical on the instructor classroom laptop for the full 250K release.

Avoid naive approaches that load the entire database and all Parquet files into memory simultaneously.

Preferred approaches may include:

- Chunked database reads
- Key-based joins
- Hash-based row comparison
- DuckDB/Polars/PyArrow for efficient Parquet processing
- Temporary comparison tables if justified

The implementation should favor correctness and diagnosability over cleverness.

## 13. Database Safety Requirements

The reconciliation must be read-only.

It must not:

- Insert records
- Update records
- Delete records
- Run migrations
- Rebuild simulator data
- Correct mismatches automatically

If possible, use a database role with read-only privileges.

## 14. Required Outputs

Each execution must create a timestamped result directory, for example:

```text
reconciliation_output/
  2026-09-22_074500_napa_250k/
```

At minimum produce:

### 14.1 Human-readable summary

`reconciliation_summary.md`

Include:

- Overall PASS / FAIL
- Release fingerprint
- Database target
- Tables/files checked
- Counts by entity
- Key mismatches
- Row-value mismatches
- Tournament-specific results
- Normalization rules used
- Any waived differences
- Final certification statement

### 14.2 Machine-readable summary

`reconciliation_summary.json`

Contain the same major metrics in structured form.

### 14.3 Entity-level mismatch files

Prefer CSV or Parquet files, for example:

```text
mismatches/
  teams_missing_in_db.csv
  teams_extra_in_db.csv
  teams_value_mismatches.csv
  team_memberships_value_mismatches.csv
  players_missing_in_db.csv
  matches_value_mismatches.csv
  ...
```

Only create empty mismatch files if that simplifies automation; otherwise omit them and record zero counts in the summary.

## 15. Console Output

Provide concise progress information and a final certification block.

Example successful result:

```text
============================================================
NAPA 250K DATASET / SIMULATOR RECONCILIATION
============================================================
Release: napa_250k

Entity                         Parquet       Database    Status
regions                            120            120      PASS
clubs                            4,xxx          4,xxx      PASS
players                        250,xxx        250,xxx      PASS
teams                        1,xxx,xxx      1,xxx,xxx      PASS
team_memberships             2,xxx,xxx      2,xxx,xxx      PASS
matches                      3,xxx,xxx      3,xxx,xxx      PASS
match_teams                  7,xxx,xxx      7,xxx,xxx      PASS
match_team_players          xx,xxx,xxx     xx,xxx,xxx      PASS
match_games                  x,xxx,xxx      x,xxx,xxx      PASS
...

Missing keys:                         0
Extra keys:                           0
Value mismatches:                     0
Tournament team mismatches:           0
Tournament membership mismatches:     0

OVERALL RELEASE CERTIFICATION: PASS
============================================================
```

Use actual values from the data; do not embed assumed counts in implementation.

## 16. Pass / Fail Criteria

### PASS

A release passes when:

- All required Parquet files and mapped database tables are available.
- Record counts match for all mapped source entities unless an explicitly documented exception exists.
- Key populations match.
- Shared source values match after approved technical normalization.
- Tournament-critical team and membership mappings match exactly.
- No unexplained reconciliation differences remain.

### FAIL

The release fails if any unexplained difference exists in:

- Record population
- IDs
- Relationships
- Tournament team membership
- Country/category
- Source values used by the simulator

A failed reconciliation must return a non-zero process exit code so it can be used in scripted validation or future CI-style workflows.

## 17. Waiver / Known-Difference Capability

Support a small explicit configuration file for known, approved differences if necessary.

Any waiver must include:

- Entity
- Key or scope
- Field if applicable
- Reason
- Approval note/comment

Waivers must be visible in the report and must never be silently applied.

The preferred target for the 250K release is **zero waivers**.

## 18. Suggested Command-Line Interface

Provide a simple repeatable command such as:

```bash
python scripts/reconcile_release.py --config config/reconciliation_250k.yml
```

Optional useful flags:

```text
--entity teams
--tournament-only
--counts-only
--output-dir <path>
--fail-fast
--verbose
```

The default command should perform the complete certification suite.

## 19. Recommended Repository Structure

Adapt to the existing simulator repository rather than forcing this exact structure, but a reasonable implementation would be:

```text
/config
  reconciliation_250k.example.yml

/scripts
  reconcile_release.py

/src/<existing_package>/reconciliation/
  __init__.py
  config.py
  parquet_reader.py
  database_reader.py
  normalizers.py
  comparator.py
  tournament_checks.py
  reporting.py

/tests/reconciliation/
  test_normalizers.py
  test_comparator.py
  test_tournament_checks.py
  test_reporting.py
```

Use the repository's existing conventions wherever possible.

## 20. Testing Requirements

Add automated tests for at least these scenarios:

1. Exact match -> PASS.
2. Missing database record -> FAIL.
3. Extra database record -> FAIL.
4. Same key but changed field -> FAIL.
5. Team membership mismatch -> FAIL.
6. Country/category mismatch -> FAIL.
7. Equivalent null/date/numeric representation -> PASS after approved normalization.
8. Intentionally defective source record present identically on both sides -> PASS reconciliation.
9. Parquet record that a student might later reject for data quality but which matches the database -> PASS reconciliation.
10. Known-difference waiver -> PASS with visible warning/waiver count.

Tests should use small fixtures and must not depend on the full 250K production dataset.

## 21. Acceptance Criteria

Implementation is complete when the instructor can:

1. Place or identify the final 250K Parquet release directory.
2. Configure a read-only connection to the classroom simulator database.
3. Run one command.
4. Receive a clear PASS/FAIL result.
5. Inspect entity-level mismatches when a failure occurs.
6. Retain the generated report as evidence of dataset-release certification.
7. Rerun the same process later to detect accidental drift or database replacement.

## 22. Final Certification Statement

When all checks pass, the summary should include language substantially equivalent to:

> **The NAPA 250K Parquet release has been reconciled against the configured tournament simulator database. The mapped source entities, identifiers, relationships, tournament teams, team memberships, and compared source values are equivalent within the documented normalization rules. This confirms source-level compatibility between the student release and the instructor simulator environment at the time of certification.**

The statement should explicitly say **source-level compatibility** so it is not confused with student downstream data-quality decisions.

## 23. Implementation Guidance for Codex

Before writing code:

1. Inspect the existing simulator repository structure.
2. Identify the existing database technology, connection utilities, ORM/models, table names, schemas, and configuration conventions.
3. Identify how the 250K database was generated and whether release/batch scoping is required.
4. Map each Parquet source file to the actual database table and key.
5. Present the proposed mapping and any ambiguities for review before implementing destructive assumptions.

Do not rewrite existing simulator functionality merely to support reconciliation. Add the capability cleanly alongside the existing application.

The implementation must remain **read-only, repeatable, auditable, configuration-driven, and usable for future release certifications**.
