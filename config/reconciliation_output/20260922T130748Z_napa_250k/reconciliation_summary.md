# NAPA Dataset / Simulator Reconciliation: napa_250k

Overall status: **FAIL**
Run timestamp: `20260922T130748Z`
Parquet root: `/path/to/napa_250k_release_directory`
Output directory: `/home/brett/projects/pickleball-sim/config/reconciliation_output/20260922T130748Z_napa_250k`
Git commit: `40e77bf86fa9e71918736ff532bd77e65685093a`

## Database Target

```json
{
  "type": "postgresql",
  "host": "localhost",
  "port": 5432,
  "database": "pickleball",
  "schema": "public",
  "user": "postgres",
  "password_env_var": "NAPA_DB_PASSWORD"
}
```

## Entity Results

| Entity | Parquet | Database | Missing | Extra | Value mismatches | Waived | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| clubs | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| club_memberships | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| match_games | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| match_team_players | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| match_teams | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| matches | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| monthly_batches | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| player_assessment_history | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| player_master | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| player_registrations | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| regions | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| team_memberships | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |
| teams | 0 | 0 | 0 | 0 | 0 | 0 | FAIL |

## Tournament-Critical Results

| Entity | Critical | Status |
| --- | --- | --- |
| match_games | yes | FAIL |
| match_team_players | yes | FAIL |
| match_teams | yes | FAIL |
| matches | yes | FAIL |
| player_master | yes | FAIL |
| team_memberships | yes | FAIL |
| teams | yes | FAIL |

## Normalization Rules

- SQL/Parquet null values normalize to null.
- Dates and timestamps compare using ISO-8601 string representation.
- Decimal values compare after rounding to 6 places.
- Floating point values compare with tolerance 1e-06.
- UUID and binary values compare using canonical string representation.

## Waivers

- None

## Certification Statement

The NAPA Parquet release is not certified against the configured tournament simulator database. One or more source-level record populations, identifiers, relationships, tournament-critical mappings, or compared source values differ.
