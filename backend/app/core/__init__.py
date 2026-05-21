"""Core application configuration and helpers.

This package uses lazy re-exports so importing a narrow dependency such as
`app.core.config` does not eagerly load generator-backed validation modules.
That keeps startup paths like standalone scripts free from circular imports.
"""

from __future__ import annotations

from importlib import import_module


_EXPORTS: dict[str, tuple[str, str]] = {
    "DEFAULT_DATABASE_URL": ("app.core.config", "DEFAULT_DATABASE_URL"),
    "SimulationSettings": ("app.core.config", "SimulationSettings"),
    "get_database_url": ("app.core.config", "get_database_url"),
    "load_default_payload_settings": (
        "app.core.config",
        "load_default_payload_settings",
    ),
    "load_settings": ("app.core.config", "load_settings"),
    "settings_from_payload": ("app.core.config", "settings_from_payload"),
    "get_configuration_payload": (
        "app.core.configuration_profiles",
        "get_configuration_payload",
    ),
    "upsert_default_configuration_profile": (
        "app.core.configuration_profiles",
        "upsert_default_configuration_profile",
    ),
    "ConfigurationFieldChange": (
        "app.core.configuration_lifecycle",
        "ConfigurationFieldChange",
    ),
    "ConfigurationLifecycleService": (
        "app.core.configuration_lifecycle",
        "ConfigurationLifecycleService",
    ),
    "ConfigurationSaveResult": (
        "app.core.configuration_lifecycle",
        "ConfigurationSaveResult",
    ),
    "ConfigurationValidationResult": (
        "app.core.configuration_lifecycle",
        "ConfigurationValidationResult",
    ),
    "compute_config_hash": (
        "app.core.configuration_lifecycle",
        "compute_config_hash",
    ),
    "diff_config_payloads": (
        "app.core.configuration_lifecycle",
        "diff_config_payloads",
    ),
    "ConfigValidationIssue": (
        "app.core.live_config_validation",
        "ConfigValidationIssue",
    ),
    "CONFIG_EDITOR_FIELDS": (
        "app.core.config_editor_metadata",
        "CONFIG_EDITOR_FIELDS",
    ),
    "CONFIG_EDITOR_SECTIONS": (
        "app.core.config_editor_metadata",
        "CONFIG_EDITOR_SECTIONS",
    ),
    "ConfigEditorFieldDefinition": (
        "app.core.config_editor_metadata",
        "ConfigEditorFieldDefinition",
    ),
    "ConfigEditorFieldState": (
        "app.core.config_editor_metadata",
        "ConfigEditorFieldState",
    ),
    "ConfigEditorOption": (
        "app.core.config_editor_metadata",
        "ConfigEditorOption",
    ),
    "ConfigEditorSectionDefinition": (
        "app.core.config_editor_metadata",
        "ConfigEditorSectionDefinition",
    ),
    "ConfigEditorSectionState": (
        "app.core.config_editor_metadata",
        "ConfigEditorSectionState",
    ),
    "build_config_editor_sections": (
        "app.core.config_editor_metadata",
        "build_config_editor_sections",
    ),
    "get_payload_value": (
        "app.core.config_editor_metadata",
        "get_payload_value",
    ),
    "DEFAULT_CONFIG_PAYLOAD": (
        "app.core.default_configuration",
        "DEFAULT_CONFIG_PAYLOAD",
    ),
    "DEFAULT_CONFIG_PROFILE_NAME": (
        "app.core.default_configuration",
        "DEFAULT_CONFIG_PROFILE_NAME",
    ),
    "DEFAULT_CONFIG_SCHEMA_VERSION": (
        "app.core.default_configuration",
        "DEFAULT_CONFIG_SCHEMA_VERSION",
    ),
    "DEFAULT_CONFIG_VERSION_NUMBER": (
        "app.core.default_configuration",
        "DEFAULT_CONFIG_VERSION_NUMBER",
    ),
    "default_config_payload": (
        "app.core.default_configuration",
        "default_config_payload",
    ),
}


__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
