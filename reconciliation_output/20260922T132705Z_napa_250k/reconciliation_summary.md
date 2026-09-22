# NAPA Dataset / Simulator Reconciliation: napa_250k

Overall status: **FAIL**
Run timestamp: `20260922T132705Z`
Parquet root: `/home/brett/projects/pickleball-sim/data/student_dataset_exports/250k_12_months_final/20260818/124204Z/clean/250k_12_months_final_initial_history`
Output directory: `/home/brett/projects/pickleball-sim/reconciliation_output/20260922T132705Z_napa_250k`
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
| clubs | 4000 | 4000 | 0 | 0 | 0 | 0 | PASS |
| club_memberships | 298069 | 298069 | 0 | 0 | 0 | 0 | PASS |
| match_games | 6116439 | 6116439 | 0 | 0 | 0 | 0 | PASS |
| match_team_players | 16312008 | 16312008 | 0 | 0 | 0 | 0 | PASS |
| match_teams | 8156004 | 8156004 | 0 | 0 | 0 | 0 | PASS |
| matches | 4078002 | 4078002 | 0 | 0 | 0 | 0 | PASS |
| monthly_batches | 12 | 1077 | 0 | 1065 | 0 | 0 | FAIL |

## Tournament-Critical Results

| Entity | Critical | Status |
| --- | --- | --- |
| match_games | yes | PASS |
| match_team_players | yes | PASS |
| match_teams | yes | PASS |
| matches | yes | PASS |

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
