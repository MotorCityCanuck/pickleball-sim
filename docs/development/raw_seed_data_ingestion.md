# Raw Seed Data Ingestion And Normalization Specification

This document defines the proposed architecture for bringing external
seed data into the pickleball simulation platform.

The project follows an ORM-first database strategy. SQLAlchemy ORM
models under `backend/app/models` are the source of truth for schema.
`backend/schema.sql` is generated from ORM metadata and must not be
hand-edited.

This is a design/specification document. The raw staging ORM models and
generated schema have been implemented; loader and normalization
implementation should follow this document while preserving the boundaries
below.

## 1. Design Goals

- Keep raw source ingestion separate from production reference-table
  normalization.

- Preserve enough raw lineage to debug source-file problems, rerun
  loads, and compare source revisions.

- Support USA and Canada seed data without recreating split production
  tables such as `usa_first_names`, `canada_first_names`,
  `usa_last_names`, or `canada_last_names`.

- Keep production tables aligned with the current consolidated schema:
  `regions`, `clubs`, `first_names`, and `last_names`.

- Make all probability and bias calculations explicit and testable.

- Avoid player generation logic in seed-data modules.

## 2. Architecture Boundary

Seed-data processing has two separate modules.

### 2.1 Raw Ingestion Module

Proposed package:

```text
backend/app/seed_data_ingest/
```

Responsibilities:

- Read raw local files and folders.

- Parse rows into staging ORM tables.

- Preserve source file path, source row number, load run, and raw row
  payload.

- Perform basic validation: required columns, parseable numbers,
  supported country/state/province codes, and non-empty required values.

- Record row-level errors without writing invalid rows to staging.

- Never write to production tables.

Non-responsibilities:

- Do not calculate production `normalized_probability`.

- Do not apply last-name regional bias rules.

- Do not create production `regions`, `clubs`, `first_names`, or
  `last_names`.

- Do not generate players or simulation entities.

### 2.2 Normalization Module

Proposed package:

```text
backend/app/seed_data_normalize/
  __init__.py
  base.py
  metro_areas.py
  first_names.py
  last_names.py
  pickleball_clubs.py
```

Responsibilities:

- Read validated rows from staging tables.

- Apply cross-table validation.

- Calculate derived production values.

- Promote rows into production reference tables.

- Replace or refresh production reference data in controlled
  transaction-safe operations.

- Own calculation logic for:
  - first-name probabilities
  - last-name probabilities
  - state/province surname bias injection
  - club-count distribution interpretation

Initial production targets:

- `regions`

- `clubs`

- `first_names`

- `last_names`

## 3. Raw Source Dataset Inventory

Initial raw source datasets:

- Metro area data: two files, one USA and one Canada.

- Pickleball club names: one file with country/state-province club name
  candidates.

- Pickleball club distribution summary: one file defining club counts by
  state/province. This belongs with the club seed-data files.

- First names: one USA folder with state-level files, including DC when
  present, and one Canada folder with 10 province files.

- Last names: one folder with two files, one USA and one Canada.

- State/province last-name bias rules: two files, one USA and one
  Canada. These belong under the last-name seed-data folder because they
  are applied during surname normalization.

Raw source files should be staged outside Git under:

```text
data/raw/
```

The root `.gitignore` should exclude `data/raw/`.

Expected local folder layout:

```text
data/raw/
  metro_areas/
  pickleball_clubs/
    names/
    distributions/
  first_names/
    us/
    ca/
  last_names/
    state_prov_biases/
```

These folders are local working directories for raw source files. They
are intentionally ignored by Git.

## 4. Common Staging Columns

Every raw staging table should include dataset-specific typed columns
plus common lineage columns.

Common columns:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `BigInteger` | Surrogate primary key. |
| `load_run_id` | `BigInteger` | FK to `raw_seed_load_runs.id`. |
| `source_file` | `String(500)` | Source file path or file name. |
| `source_row_number` | `Integer` | 1-based row number from source file. |
| `raw_payload` | `JSONB` | Original parsed row values. |
| `created_at` | `DateTime` | From `TimestampMixin`. |
| `updated_at` | `DateTime` | From `TimestampMixin`, where used consistently. |

Staging tables should use typed columns for fields required by
normalization. `raw_payload` is for audit/debugging, not primary query
logic.

## 5. Load Tracking Tables

### 5.1 `raw_seed_load_runs`

Tracks one attempt to load one dataset or file group.

Recommended columns:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `BigInteger` | Primary key. |
| `dataset_type` | `String(80)` | Example: `metro_areas`, `first_names_us`. |
| `source_path` | `String(1000)` | File or directory path supplied to CLI. |
| `source_file_count` | `Integer` | Number of files discovered for the run. |
| `source_checksum` | `String(128)` | Optional hash of file names and contents. |
| `started_at` | `DateTime` | Set when load starts. |
| `completed_at` | `DateTime` | Set on completed or failed run. |
| `status` | `String(30)` | `pending`, `running`, `completed`, `failed`. |
| `rows_read` | `Integer` | Total raw rows read. |
| `rows_loaded` | `Integer` | Valid rows inserted into staging. |
| `rows_rejected` | `Integer` | Invalid rows recorded as errors. |
| `error_message` | `Text` | Run-level failure message. |
| `created_at` | `DateTime` | From `TimestampMixin`. |
| `updated_at` | `DateTime` | From `TimestampMixin`. |

Recommended constraints:

- `dataset_type` is not null.

- `status` is one of `pending`, `running`, `completed`, `failed`.

- Row counts are non-negative.

### 5.2 `raw_seed_load_errors`

Stores row-level or file-level parsing and validation errors.

Recommended columns:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `BigInteger` | Primary key. |
| `load_run_id` | `BigInteger` | FK to `raw_seed_load_runs.id`. |
| `source_file` | `String(500)` | Source file path or file name. |
| `source_row_number` | `Integer` | Nullable for file-level errors. |
| `error_code` | `String(80)` | Stable machine-readable code. |
| `error_message` | `Text` | Human-readable explanation. |
| `raw_payload` | `JSONB` | Raw row values when available. |
| `created_at` | `DateTime` | From `TimestampMixin`. |

## 6. Staging Tables

### 6.1 `raw_metro_areas`

Purpose: stage metro area and population source rows before
normalization into `regions` or future region-reference tables.

Source files:

- One USA regional MSA file.

- One Canada regional MSA file.

Both files use:

```text
COUNTRY,
Metro Area Name,
State/Prov,
Population,
Probability
```

Dataset-specific typed columns:

| Column | Type | Source |
| --- | --- | --- |
| `country_code` | `String(2)` | Normalized from `COUNTRY`. |
| `state_province_code` | `String(10)` | Normalized from `State/Prov`. |
| `metro_area_name` | `String(255)` | `Metro Area Name`. |
| `population` | `BigInteger` | `Population`. |
| `selection_probability` | `Numeric(12,8)` | `Probability`. |
| `source_dataset` | `String(255)` | Loader-supplied source label. |

Validation:

- `country_code` must be `US` or `CA`.

- `state_province_code` must be present.

- `metro_area_name` must be present.

- `population` must be positive.

- `selection_probability` must be non-negative.

Normalization notes:

- The production `regions` table currently represents regions with
  fields such as country, state/province, region name, population, and
  competitiveness multiplier.

- `selection_probability` is required by downstream regional player
  allocation logic and should be promoted into production `regions`.
  This requires adding a nullable `selection_probability` column to the
  `regions` ORM model during implementation.

### 6.2 `raw_pickleball_club_names`

Purpose: stage candidate pickleball club names by country and
state/province.

Source columns:

```text
club_seed,
country,
state_prov,
club_name,
club_type,
size_tier,
generation_method
```

Dataset-specific typed columns:

| Column | Type | Source |
| --- | --- | --- |
| `club_seed` | `BigInteger` | `club_seed`. |
| `country_code` | `String(2)` | Normalized from `country`. |
| `state_province_code` | `String(10)` | Normalized from `state_prov`. |
| `club_name` | `String(255)` | `club_name`. |
| `club_type` | `String(80)` | `club_type`. |
| `size_tier` | `String(30)` | `size_tier`. |
| `generation_method` | `String(100)` | `generation_method`. |
| `source_dataset` | `String(255)` | Loader-supplied source label. |

Validation:

- `club_seed` must be present and parseable as an integer.

- `country_code` must be `US` or `CA`.

- `state_province_code` and `club_name` must be present.

- Duplicate `club_seed` values within the same load run should be
  rejected or reported.

Normalization notes:

- `club_seed` is the source identifier. The staging table still uses its
  own surrogate `id`.

- Production club creation should use this table together with
  `raw_pickleball_club_distributions`.

### 6.3 `raw_pickleball_club_distributions`

Purpose: stage target club counts by country and state/province.

Source columns:

```text
country,
state_prov_code,
state_prov_name,
club_count
```

Dataset-specific typed columns:

| Column | Type | Source |
| --- | --- | --- |
| `country_code` | `String(2)` | Normalized from `country`. |
| `state_province_code` | `String(10)` | Normalized from `state_prov_code`. |
| `state_province_name` | `String(255)` | `state_prov_name`. |
| `target_club_count` | `Integer` | `club_count`. |
| `source_dataset` | `String(255)` | Loader-supplied source label. |

Validation:

- `country_code` must be `US` or `CA`.

- `state_province_code` and `state_province_name` must be present.

- `target_club_count` must be zero or positive.

Normalization notes:

- Production club normalization uses `target_club_count` to determine
  how many clubs to create or refresh for each state/province.

- If there are fewer candidate names than requested clubs for a
  state/province, normalization must define whether to fail, sample with
  replacement, or fall back to broader country-level names.

### 6.4 `raw_first_names`

Purpose: stage first-name frequency rows by country, state/province,
birth year, and gender.

Source files:

- USA: one folder containing state-level files, one file per state plus
  DC when present.

- Canada: one folder containing 10 province files, one file per
  province.

Both countries use the same logical layout:

```text
state/province code,
sex,
birth_year,
name,
occurrences
```

Known country-specific heading:

- Canada province code heading: `Prov_code`.

- USA state code heading: state-code column from the USA files.

Example:

```text
NE,F,1910,Mary,161
```

Dataset-specific typed columns:

| Column | Type | Source |
| --- | --- | --- |
| `country_code` | `String(2)` | Derived from dataset being loaded. |
| `state_province_code` | `String(10)` | State/province source column. |
| `gender` | `String(1)` | `sex`; expected `M` or `F`. |
| `birth_year` | `Integer` | `birth_year`. |
| `first_name` | `String(100)` | `name`. |
| `frequency_count` | `Integer` | `occurrences`. |
| `source_dataset` | `String(255)` | Loader-supplied source label. |

Validation:

- `country_code` must be `US` or `CA`.

- `state_province_code` must be present.

- `gender` must be `M` or `F`.

- `birth_year` must be parseable as an integer.

- `first_name` must be present.

- `frequency_count` must be positive.

Normalization notes:

- Production target is `first_names`.

- `normalized_probability` is calculated during normalization, not raw
  ingestion.

- The probability cohort is:

```text
country_code,
state_province_code,
birth_year,
gender
```

- Formula:

```text
normalized_probability =
  frequency_count /
  sum(frequency_count for the same cohort)
```

- Probabilities are stored as `NUMERIC(12,8)` and should sum to
  approximately `1.0` per cohort, subject to rounding.

### 6.5 `raw_last_names`

Purpose: stage country-level last-name frequency rows.

Source files:

- One USA last-name file.

- One Canada last-name file.

Both files use:

```text
name,
num_of_occurrences
```

Dataset-specific typed columns:

| Column | Type | Source |
| --- | --- | --- |
| `country_code` | `String(2)` | Derived from source file identity. |
| `last_name` | `String(100)` | `name`. |
| `frequency_count` | `Integer` | `num_of_occurrences`. |
| `source_dataset` | `String(255)` | Loader-supplied source label. |

Validation:

- `country_code` must be `US` or `CA`.

- `last_name` must be present.

- `frequency_count` must be positive.

Normalization notes:

- Raw last-name files are country-level.

- Production target `last_names` is state/province-level because the
  current production table includes `country_code` and
  `state_province_code`.

- Normalization expands country-level surname frequencies into
  state/province-level production rows.

- `raw_state_prov_biases` is applied during this expansion.

### 6.6 `raw_state_prov_biases`

Purpose: stage state/province surname bias rules. These rules emphasize
specific surnames in specific states or provinces during last-name
normalization.

Source files:

- One USA bias file.

- One Canada bias file.

Both files use:

```text
state_prov,
last_name,
bias_multiplier,
bias_reason
```

Dataset-specific typed columns:

| Column | Type | Source |
| --- | --- | --- |
| `country_code` | `String(2)` | Derived from source file identity. |
| `state_province_code` | `String(10)` | `state_prov`. |
| `last_name` | `String(100)` | `last_name`. |
| `bias_multiplier` | `Numeric(10,4)` | `bias_multiplier`. |
| `bias_reason` | `Text` | `bias_reason`. |
| `source_dataset` | `String(255)` | Loader-supplied source label. |

Validation:

- `country_code` must be `US` or `CA`.

- `state_province_code` and `last_name` must be present.

- `bias_multiplier` must be positive.

- `bias_reason` may be nullable but should be preserved when present.

Normalization notes:

- Bias rules are not applied during raw ingestion.

- Bias rules are applied when preparing production `last_names`.

- If a bias rule references a surname that is missing from
  `raw_last_names` for that country, normalization should report it as a
  warning or validation error. The first implementation should fail
  normalization for unresolved bias-rule surnames unless explicitly
  configured otherwise.

## 7. Normalization Algorithms

### 7.1 First-Name Normalization

Input:

- `raw_first_names`

Output:

- `first_names`

Algorithm:

1. Select one or more completed raw first-name load runs.

2. Group rows by:

```text
country_code,
state_province_code,
birth_year,
gender
```

3. For each group, calculate total `frequency_count`.

4. Insert production `first_names` rows with:

```text
normalized_probability =
  frequency_count / cohort_total
```

5. Store the source dataset label for traceability.

Replacement behavior:

- First implementation should replace production `first_names` for the
  selected country or country/state scope inside a single transaction.

### 7.2 Last-Name Normalization With Bias Injection

Input:

- `raw_last_names`

- `raw_state_prov_biases`

- state/province scope from `raw_metro_areas`,
  `raw_pickleball_club_distributions`, or an explicit state/province
  list.

Output:

- `last_names`

Recommended first-pass algorithm:

1. Select country-level surname rows for one country.

2. For each target state/province in that country, copy the country-level
   surname rows into an in-memory state/province cohort.

3. For each surname in that state/province cohort, calculate:

```text
adjusted_frequency =
  frequency_count * matching_bias_multiplier
```

4. If no bias rule exists for a surname in that state/province, use a
   default multiplier of `1.0`.

5. Sum adjusted frequencies within the state/province cohort.

6. Insert production `last_names` rows with:

```text
normalized_probability =
  adjusted_frequency / adjusted_frequency_total
```

7. Store the original country-level frequency, the applied bias factor,
   and the final adjusted state/province frequency.

8. Store the original source dataset label.

Replacement behavior:

- First implementation should replace production `last_names` for the
  selected country or country/state scope inside a single transaction.

Production schema implication:

- The existing `last_names.frequency_count` should store the original
  country-level raw surname count.

- Add nullable `bias_multiplier NUMERIC(10,4)` to production
  `last_names`.

- Add nullable `adjusted_frequency_count NUMERIC(18,4)` to production
  `last_names`.

- `last_names.normalized_probability` should be calculated from
  `adjusted_frequency_count` within each country/state-province cohort.

### 7.3 Metro Area Normalization

Input:

- `raw_metro_areas`

Output:

- `regions`

Recommended first-pass behavior:

- Create or refresh one `regions` row per metro area.

- If multiple raw rows share the same production metro-area natural key
  (`country_code`, `state_province_code`, `metro_area_name`), aggregate
  them into one production `regions` row by summing `population` and
  `selection_probability`.

- Map:
  - `country_code` -> `regions.country_code`
  - `state_province_code` -> `regions.state_province_code`
  - `metro_area_name` -> `regions.region_name`
  - `population` -> `regions.population`
  - `selection_probability` -> `regions.selection_probability`

- Store `region_type` as a stable value such as `metro`.

- Enforce metro-area uniqueness by country, state/province, and region name:
  `regions(country_code, state_province_code, region_name)`.

### 7.4 Club Normalization

Input:

- `raw_pickleball_club_names`

- `raw_pickleball_club_distributions`

Output:

- `clubs`

Recommended first-pass behavior:

1. For each country/state-province distribution row, read
   `target_club_count`.

2. Select candidate club names from `raw_pickleball_club_names` for the
   same country/state-province.

3. Create up to `target_club_count` production clubs.

4. Preserve club type and size tier where compatible with production
   `clubs`.

Replacement behavior:

- Club normalization replaces all production `clubs` for both countries
  when run.

Shortage behavior:

- If a state/province has fewer staged candidate club names than
  `target_club_count`, normalization should log an error for that load.

- Missing club-name slots should still be filled with a placeholder club
  name:

```text
Not Enough Club Names
```

- The placeholder makes the shortage visible in downstream validation
  while allowing the normalization run to complete.

- Each production club links to one and only one `regions` row through
  the existing `clubs.region_id` relationship.

- Do not introduce a many-to-many club/region association for seed-data
  normalization.

- Club normalization should assign each generated club to a single
  eligible region in the same country/state-province. The first
  implementation may use deterministic weighted assignment across metro
  regions using `regions.selection_probability`.

## 8. Reload, Replacement, And Index Semantics

Raw staging behavior:

- Raw staging is full-replace by dataset.

- Each CLI run creates one `raw_seed_load_runs` record.

- Before loading a dataset, the raw ingestion module truncates or deletes
  existing rows for that dataset's staging table.

- The new staged rows retain the current `load_run_id`.

- Invalid rows are captured in `raw_seed_load_errors`.

- Prior staged raw rows for that dataset are not retained after a
  successful replacement load.

- Prior `raw_seed_load_runs` and `raw_seed_load_errors` records should be
  retained for audit history unless a later cleanup utility is added.

- If a load fails, the staging table should remain in its previous valid
  state when possible. The first implementation should perform
  truncation and replacement inside a transaction so failed loads roll
  back.

Index behavior:

- Staging-table lookup indexes should be declared in ORM metadata.

- For large raw loads, the ingestion workflow may defer creation or
  rebuilding of non-primary-key staging indexes until after data rows are
  loaded successfully.

- The load should be considered successful only after required staging
  indexes are present and usable.

- Index creation/rebuild work must remain ORM-first. If explicit
  post-load index management is implemented, it should use named indexes
  that match the ORM metadata and should be covered by tests.

Normalization behavior:

- Explicit replacement by dataset and scope.

- Replacement must be transaction-safe.

- CLI should require a deliberate flag for destructive production
  refreshes, for example:

```text
--replace-production
```

Cleanup behavior:

- Add a cleanup/purge utility for raw seed load history.

- When run, it should purge `raw_seed_load_runs`,
  `raw_seed_load_errors`, and related raw staging rows older than 30
  days.

- The purge applies to all load runs older than 30 days, including
  completed and failed runs.

- The utility should be explicit and manually invoked; it should not run
  automatically as part of normal ingestion or normalization.

- Proposed script:

```text
backend/scripts/purge_raw_seed_loads.py
```

- Default behavior:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 backend/scripts/purge_raw_seed_loads.py \
  --older-than-days 30
```

## 9. CLI Design

### 9.1 Raw Ingestion CLI

Proposed script:

```text
backend/scripts/load_raw_seed_data.py
```

Example:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 backend/scripts/load_raw_seed_data.py \
  --dataset first_names_us \
  --input-dir data/raw/first_names/us
```

Dataset-to-folder defaults:

| Dataset | Default path |
| --- | --- |
| `metro_areas_us` | `data/raw/metro_areas/` |
| `metro_areas_ca` | `data/raw/metro_areas/` |
| `pickleball_club_names` | `data/raw/pickleball_clubs/names/` |
| `pickleball_club_distributions` | `data/raw/pickleball_clubs/distributions/` |
| `first_names_us` | `data/raw/first_names/us/` |
| `first_names_ca` | `data/raw/first_names/ca/` |
| `last_names_us` | `data/raw/last_names/` |
| `last_names_ca` | `data/raw/last_names/` |
| `state_prov_biases_us` | `data/raw/last_names/state_prov_biases/` |
| `state_prov_biases_ca` | `data/raw/last_names/state_prov_biases/` |

Initial supported dataset values:

- `metro_areas_us`

- `metro_areas_ca`

- `pickleball_club_names`

- `pickleball_club_distributions`

- `first_names_us`

- `first_names_ca`

- `last_names_us`

- `last_names_ca`

- `state_prov_biases_us`

- `state_prov_biases_ca`

### 9.2 Normalization CLI

Proposed script:

```text
backend/scripts/normalize_seed_data.py
```

Example:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 backend/scripts/normalize_seed_data.py \
  --dataset first_names \
  --country US \
  --replace-production
```

Initial supported dataset values:

- `metro_areas`

- `pickleball_clubs`

- `first_names`

- `last_names`

## 10. ORM And Schema Change Plan

When approved, implementation should follow the ORM-first workflow:

1. Add ORM models under `backend/app/models`.

2. Import/export models through `backend/app/models/__init__.py`.

3. Update `backend/tests/schema_expectations.py`.

4. Update ORM consistency tests for table count, indexes, constraints,
   and key columns.

5. Regenerate `backend/schema.sql` with:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 backend/scripts/export_schema_from_orm.py
```

6. Run offline tests:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 -m pytest backend/tests backend/test_models.py -q
```

7. Recreate the local development database only when intentionally
   verifying DB behavior:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 backend/scripts/recreate_db_from_orm.py --yes
```

8. Run opt-in DB smoke tests:

```bash
RUN_DB_TESTS=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 -m pytest \
  backend/tests/test_database_smoke.py backend/tests/test_db_session.py backend/test_models.py -q
```

## 11. Proposed Table List

New staging and tracking tables proposed by this spec:

- `raw_seed_load_runs`

- `raw_seed_load_errors`

- `raw_metro_areas`

- `raw_pickleball_club_names`

- `raw_pickleball_club_distributions`

- `raw_first_names`

- `raw_last_names`

- `raw_state_prov_biases`

This would increase the ORM table count by 8.

Production table changes tracked by this spec:

- `regions.selection_probability NUMERIC(12,8)` is available for metro
  area normalization.

- Add nullable `bias_multiplier NUMERIC(10,4)` to `last_names`.

- Add nullable `adjusted_frequency_count NUMERIC(18,4)` to
  `last_names`.

These production-column changes must be made in the ORM models first and
then reflected in `backend/schema.sql` by regenerating from ORM metadata.

## 12. Testing Strategy

Raw ingestion tests:

- Parser tests for each source format.

- Required-column validation tests.

- Type coercion tests for integers and decimals.

- Row-level error capture tests.

- Load-run status transition tests.

Normalization tests:

- First-name cohort probability tests.

- Last-name bias multiplier tests.

- Last-name unresolved bias-rule tests.

- Club distribution count tests.

- Metro-area promotion tests.

DB smoke tests:

- Verify staging tables exist.

- Insert one valid row per staging table.

- Verify key constraints reject invalid country/status/frequency values.

## 13. Open Review Questions

No open questions remain for the first implementation pass.
