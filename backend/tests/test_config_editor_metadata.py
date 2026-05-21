"""Tests for metadata scaffolding behind the future config editor."""
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import (  # noqa: E402
    CONFIG_EDITOR_FIELDS,
    CONFIG_EDITOR_SECTIONS,
    build_config_editor_sections,
    default_config_payload,
    get_payload_value,
)


def test_config_editor_field_paths_are_unique():
    paths = [field.path for field in CONFIG_EDITOR_FIELDS]
    assert len(paths) == len(set(paths))


def test_config_editor_sections_only_reference_declared_fields():
    declared_paths = {field.path for field in CONFIG_EDITOR_FIELDS}

    for section in CONFIG_EDITOR_SECTIONS:
        assert section.field_paths
        for path in section.field_paths:
            assert path in declared_paths


def test_default_payload_provides_values_for_scaffolded_fields():
    payload = default_config_payload()

    missing = [
        field.path
        for field in CONFIG_EDITOR_FIELDS
        if get_payload_value(payload, field.path) is None
    ]

    assert missing == []


def test_build_config_editor_sections_attaches_current_values():
    payload = default_config_payload()
    payload["simulation"]["master_seed"] = 123
    payload["club_generation"]["cross_region_assignment_enabled"] = True

    sections = build_config_editor_sections(payload)
    field_states = {
        field.definition.path: field
        for section in sections
        for field in section.fields
    }

    assert field_states["simulation.master_seed"].value == 123
    assert field_states["simulation.master_seed"].is_default_value is False
    assert (
        field_states["club_generation.cross_region_assignment_enabled"].value
        is True
    )
    assert field_states["club_generation.cross_region_assignment_enabled"].is_present_in_payload is True


def test_get_payload_value_returns_none_for_missing_path():
    payload = default_config_payload()

    assert get_payload_value(payload, "simulation.not_real") is None
    assert get_payload_value(payload, "not_real") is None
