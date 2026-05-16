# ORM Standards

This document defines SQLAlchemy ORM standards for the Pickleball Simulation
Platform. These standards apply to models under `backend/app/models`.

## Purpose

The ORM layer exists for Python data access, relationship navigation, query
composition, and application-level readability.

The ORM layer is not the authoritative schema management mechanism.

## Schema Authority

The project uses a DDL-first database strategy.

- The authoritative executable schema is `backend/schema.sql`.
- SQLAlchemy models must match the DDL.
- SQLAlchemy models must not introduce schema behavior that is absent from the
  DDL unless the DDL is updated first.
- Alembic migrations are not part of the current schema workflow.
- Do not use `Base.metadata.create_all()` as a production schema creation path.
- Any schema change must be made in DDL first, then reflected in the ORM.

## Current Live Model Scope

The current live schema and ORM define 22 tables:

1. `generation_runs`
2. `regions`
3. `monthly_batches`
4. `players`
5. `player_rating_history`
6. `player_assessment_history`
7. `player_registrations`
8. `clubs`
9. `club_memberships`
10. `teams`
11. `team_memberships`
12. `tournaments`
13. `matches`
14. `match_teams`
15. `match_team_players`
16. `first_names`
17. `last_names`
18. `batch_runs`
19. `uploaded_files`
20. `export_runs`
21. `validation_results`
22. `job_status`

The reference-name design uses consolidated `first_names` and `last_names`
tables with `country_code`, rather than separate USA and Canada tables.

## Naming Standards

- Table names use plural `snake_case`.
- Column names use `snake_case`.
- Primary keys are named `id`.
- Foreign keys are named `{referenced_entity}_id`.
- ORM class names use singular `PascalCase`.
- ORM module names use the table name, for example `players.py`.
- Constraint names must be explicit and stable.
- Index names in DDL must be explicit and stable.

## Model File Standards

Each model file should contain one primary ORM class.

Required structure:

- Module docstring describing the table purpose.
- SQLAlchemy imports.
- Local imports from `.base`.
- ORM class definition.
- Columns.
- Relationships.
- Constraints in `__table_args__`.
- Optional `__repr__` for high-value domain entities.

Avoid:

- Unused imports.
- Duplicated timestamp definitions when `TimestampMixin` matches the DDL.
- Business logic in model classes.
- Data generation logic in model classes.
- Query-heavy helper methods in model classes.

## Base And Timestamp Standards

All models must inherit from `Base`.

Use `TimestampMixin` only when the DDL includes both:

- `created_at`
- `updated_at`

If the DDL includes only `created_at`, define only `created_at` in that model.
Do not add `updated_at` in ORM unless the DDL has it.

Timestamp columns should use database-side defaults matching the DDL:

```python
server_default=text("CURRENT_TIMESTAMP")
```

## Column Standards

Column definitions must match DDL for:

- Type
- Length
- Precision and scale
- Nullability
- Server defaults
- Uniqueness
- Foreign keys
- Check constraints

Use PostgreSQL dialect types where the DDL requires them:

- `UUID(as_uuid=True)` for UUID columns
- `JSONB` for JSONB columns

Numeric precision must be explicit where the DDL is explicit, for example:

```python
Numeric(8, 3)
Numeric(8, 4)
Numeric(5, 2)
```

## Default Standards

Server defaults must be valid SQL expressions.

Correct:

```python
server_default=text("'pending'")
server_default=text("'ACTIVE'")
server_default=text("CURRENT_TIMESTAMP")
server_default=text("gen_random_uuid()")
```

Incorrect:

```python
server_default=text("pending")
server_default=text("ACTIVE")
```

Python-side `default=` may be used for ORM object convenience, but it must not
conflict with the DDL server default.

## Constraint Standards

ORM constraints should mirror DDL constraints.

Use explicit names for:

- `CheckConstraint`
- `UniqueConstraint`
- Foreign key constraints when the DDL names them

Prefer SQL string constraints when that most directly mirrors the DDL.

Example:

```python
CheckConstraint(
    "status IN ('pending', 'running', 'completed', 'failed')",
    name="chk_run_status",
)
```

Do not add ORM constraints that are absent from DDL unless the DDL is updated
first.

## Relationship Standards

Relationships should be defined for navigability, not as schema authority.

Required standards:

- Define relationships for all important foreign keys.
- Use `back_populates` when both sides of a relationship are declared.
- Do not declare `back_populates` on only one side.
- Use `order_by` only when the ordering is a consistent domain expectation.
- Avoid cascade behavior unless explicitly required and reflected in the
  intended database behavior.
- Avoid eager loading defaults unless there is a measured query need.

Recommended parent-child naming:

- Collection relationships use plural names, for example `rating_history`.
- Scalar relationships use singular names, for example `generation_run`.

## Foreign Key Standards

Foreign key columns must match DDL exactly.

Required:

- Use the correct target table and column.
- Preserve nullability from DDL.
- Preserve indexes where the ORM intentionally documents them.
- Do not add application-level FK assumptions if the DDL does not enforce them.

Known current example: `matches.winning_team_id` is a plain `BIGINT` in the DDL,
not a foreign key. The ORM should not convert it into a `ForeignKey` unless the
DDL is changed first.

## Historical Data Standards

The platform stores mutable player state historically.

Required:

- Do not add `age` to `players`; calculate it from `birth_date`.
- Do not add current rating fields to `players`.
- Ratings belong in `player_rating_history`.
- Assessment values belong in `player_assessment_history`.
- New player intake belongs in `player_registrations`.
- Match, rating, and assessment records must retain their batch association
  where required by DDL.

Historical records should be treated as append-oriented unless a documented
repair workflow requires correction.

## Batch Association Standards

Monthly simulation output must be traceable to `monthly_batches`.

Tables with required batch associations include:

- `player_rating_history`
- `player_assessment_history`
- `player_registrations`
- `matches`
- `batch_runs`

Optional batch associations are allowed only where the DDL allows nulls, such
as `export_runs.batch_id` and `validation_results.batch_id`.

## Reference Data Standards

The live reference-name design uses consolidated tables:

- `first_names`
- `last_names`

Both include `country_code`.

Do not add country-specific reference-name ORM models unless the live DDL is
changed back to that design.

## Operational Table Standards

Operational tables track execution, files, exports, validation, and jobs.

Status-like fields must:

- Use explicit check constraints matching DDL.
- Use lowercase values unless DDL uses uppercase values.
- Preserve existing DDL vocabulary exactly.

Examples:

- `generation_runs.status`
- `monthly_batches.processing_status`
- `batch_runs.run_status`
- `job_status.status`

## Import And Registry Standards

Every live ORM model must be imported in `backend/app/models/__init__.py`.

The model registry must expose:

- `Base`
- `TimestampMixin`
- Every live ORM class

Adding a model is incomplete until:

- The DDL exists.
- The ORM class exists.
- The class is imported by `backend/app/models/__init__.py`.
- Metadata import tests pass.

## Test Standards

ORM tests should be split into two categories.

Metadata tests:

- Must not require a live PostgreSQL server.
- Import all models.
- Assert the expected table count.
- Assert expected table names.
- Optionally compare ORM columns against parsed DDL.

Database integration tests:

- May require PostgreSQL.
- Must use configurable connection settings.
- Must not hardcode private IP addresses.
- Should be skipped or clearly marked when a database is unavailable.

## Documentation Standards

When ORM or DDL changes are made, update documentation that describes:

- Table count.
- Table names.
- Reference data table strategy.
- Required model scope.
- Any unresolved architecture decisions.

If a planning document is stale but still useful, add a current-status note
instead of silently implementing against stale references.

## Pre-Implementation Checklist

Before adding or changing an ORM model:

- Confirm the intended table exists in `backend/schema.sql`.
- Confirm whether the change is schema-level or ORM-only.
- If schema-level, update DDL first.
- Match column types, nullability, defaults, and constraints exactly.
- Add or update relationships consistently on both sides.
- Import the model in `backend/app/models/__init__.py`.
- Run metadata import tests.
- Run database integration tests only when a configured database is available.

## Current Open Decisions

These items should be resolved before major implementation work:

- Whether `backend/schema.sql` or the long database design document is the
  practical day-to-day source of truth.
- Whether `generation_parameters` is still required as a separate table, or
  whether `generation_runs.parameter_snapshot` fully replaces it.
- Whether `matches.winning_team_id` should remain a plain integer or become a
  foreign key to `match_teams.id`.
- Whether all relationship pairs should be normalized to `back_populates`.
