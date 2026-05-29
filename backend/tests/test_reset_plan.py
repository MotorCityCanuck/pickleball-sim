"""Tests for shared runtime reset-domain classification."""
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generation.reset_plan import (  # noqa: E402
    CONTROL_PLANE_PRESERVED_MODELS,
    GENERATED_OPERATIONAL_REBUILDABLE_MODELS,
    RAW_SEED_HISTORY_PRESERVED_MODELS,
    RAW_SEED_STAGING_REBUILDABLE_MODELS,
    REFERENCE_SEED_REBUILDABLE_MODELS,
    RESET_DOMAIN_PLANS,
)
from app.models import (  # noqa: E402
    ExportRun,
    GenerationRun,
    GenerationRuntimeMetric,
    JobStageProgress,
    Match,
    MatchTeam,
    MatchTeamPlayer,
    MonthlyBatch,
    Player,
    RatingsUpdateLog,
    Region,
    StudentDatasetRelease,
)


def test_reset_domain_plans_do_not_overlap():
    seen_models: set[type[object]] = set()

    for domain in RESET_DOMAIN_PLANS:
        domain_models = set(domain.models)
        assert not seen_models.intersection(domain_models)
        seen_models.update(domain_models)


def test_reset_plan_marks_preserved_history_tables_explicitly():
    assert GenerationRun in CONTROL_PLANE_PRESERVED_MODELS
    assert MonthlyBatch in CONTROL_PLANE_PRESERVED_MODELS
    assert JobStageProgress in CONTROL_PLANE_PRESERVED_MODELS
    assert GenerationRuntimeMetric in CONTROL_PLANE_PRESERVED_MODELS
    assert ExportRun in CONTROL_PLANE_PRESERVED_MODELS
    assert StudentDatasetRelease in CONTROL_PLANE_PRESERVED_MODELS


def test_reset_plan_marks_generated_operational_tables_as_rebuildable():
    assert RatingsUpdateLog in GENERATED_OPERATIONAL_REBUILDABLE_MODELS
    assert MatchTeamPlayer in GENERATED_OPERATIONAL_REBUILDABLE_MODELS
    assert MatchTeam in GENERATED_OPERATIONAL_REBUILDABLE_MODELS
    assert Match in GENERATED_OPERATIONAL_REBUILDABLE_MODELS
    assert Player in GENERATED_OPERATIONAL_REBUILDABLE_MODELS


def test_reset_plan_separates_reference_and_raw_seed_domains():
    assert Region in REFERENCE_SEED_REBUILDABLE_MODELS
    assert RAW_SEED_HISTORY_PRESERVED_MODELS
    assert RAW_SEED_STAGING_REBUILDABLE_MODELS
