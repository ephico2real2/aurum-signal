"""Shared payload contracts for cross-component JSON (AURUM, BRIDGE, FORGE)."""

# Keep in sync with schemas/manifest.json "version"
SCHEMA_BUNDLE_VERSION = "1.0.0"

from .aurum_forge import (
    VALID_MODES,
    forge_open_group_from_bridge,
    normalize_aurum_open_trade,
    validate_aurum_cmd,
    validate_forge_command,
)

__all__ = [
    "SCHEMA_BUNDLE_VERSION",
    "VALID_MODES",
    "forge_open_group_from_bridge",
    "normalize_aurum_open_trade",
    "validate_aurum_cmd",
    "validate_forge_command",
]
