"""Reads `outpost.yaml` into domain values. The only layer that knows the file format."""

from outpost.config.loader import load_config, parse_config

__all__ = ["load_config", "parse_config"]
