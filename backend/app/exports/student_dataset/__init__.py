"""Student-facing dataset export contract."""

from .projection import (
    EXCLUDED_SOURCE_TABLES,
    PROJECTION_BY_TABLE,
    STUDENT_DATASET_SCHEMA_VERSION,
    STUDENT_TABLE_ORDER,
    ProjectionDriftError,
    RelationshipValidation,
    SourceFilterSpec,
    StudentTableProjection,
    TemporalValidation,
    get_projection,
    validate_projection_contract,
)

__all__ = [
    "EXCLUDED_SOURCE_TABLES",
    "PROJECTION_BY_TABLE",
    "STUDENT_DATASET_SCHEMA_VERSION",
    "STUDENT_TABLE_ORDER",
    "ProjectionDriftError",
    "RelationshipValidation",
    "SourceFilterSpec",
    "StudentTableProjection",
    "TemporalValidation",
    "get_projection",
    "validate_projection_contract",
]
