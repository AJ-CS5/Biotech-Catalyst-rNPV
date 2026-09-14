"""Loading and validation of asset assumptions files.

:func:`validate` is pure: it takes an already-parsed mapping and returns every
violation it can find, in file order, without touching the filesystem or the
network. :func:`load_asset_config` is the only function here that reads a file.

No model mathematics lives in this module.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import yaml

from catalyst_rnpv.schema import (
    CATALYST_KEYS,
    DISTRIBUTION_KEYS,
    DISTRIBUTION_PARAMS,
    PARAMETER_FIELDS,
    SOURCE_TYPES,
    STATUSES,
    TOP_LEVEL_KEYS,
    AssetConfig,
    ConfigError,
    Distribution,
    Parameter,
)

__all__ = [
    "AssetConfig",
    "ConfigError",
    "Distribution",
    "Parameter",
    "load_asset_config",
    "validate",
]

_STRING_TOP_LEVEL = ("asset_id", "asset_name", "company", "ticker")


def _is_number(obj: Any) -> bool:
    return isinstance(obj, (int, float)) and not isinstance(obj, bool)


def _as_date(obj: Any) -> datetime.date | None:
    """Coerce an ISO date string or date object to a date, or return None."""
    if isinstance(obj, datetime.datetime):
        return obj.date()
    if isinstance(obj, datetime.date):
        return obj
    if isinstance(obj, str):
        try:
            return datetime.date.fromisoformat(obj)
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def _validate_catalyst(block: Any, errors: list[str]) -> None:
    if not isinstance(block, dict):
        errors.append("catalyst: expected a mapping")
        return
    for key in sorted(set(block) - CATALYST_KEYS):
        errors.append(f"catalyst.{key}: unknown key")
    for key in sorted(CATALYST_KEYS - set(block)):
        errors.append(f"catalyst.{key}: missing required key")
    for key in sorted(CATALYST_KEYS & set(block)):
        if not isinstance(block[key], str) or not block[key].strip():
            errors.append(f"catalyst.{key}: expected a non-empty string")


def _validate_distribution(key: str, dist: Any, errors: list[str]) -> None:
    if not isinstance(dist, dict):
        errors.append(f"{key}.distribution: expected a mapping or null")
        return

    for unknown in sorted(set(dist) - DISTRIBUTION_KEYS):
        errors.append(f"{key}.distribution.{unknown}: unknown key")

    dist_type = dist.get("type")
    if not isinstance(dist_type, str):
        errors.append(f"{key}.distribution.type: missing or not a string")
        return
    if dist_type not in DISTRIBUTION_PARAMS:
        allowed = ", ".join(sorted(DISTRIBUTION_PARAMS))
        errors.append(f"{key}.distribution.type: unknown type {dist_type!r} (allowed: {allowed})")
        return

    params = dist.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        errors.append(f"{key}.distribution.params: expected a mapping")
        return

    required = DISTRIBUTION_PARAMS[dist_type]
    for missing in sorted(required - set(params)):
        errors.append(f"{key}.distribution.params.{missing}: missing for type {dist_type!r}")
    for extra in sorted(set(params) - required):
        errors.append(f"{key}.distribution.params.{extra}: unexpected for type {dist_type!r}")

    numeric: dict[str, float] = {}
    for name in sorted(required & set(params)):
        raw_value = params[name]
        if not _is_number(raw_value):
            errors.append(f"{key}.distribution.params.{name}: expected a number")
        else:
            numeric[name] = float(raw_value)

    if set(numeric) != set(required):
        return  # cannot check ranges without every parameter

    if dist_type == "bernoulli" and not 0.0 <= numeric["p"] <= 1.0:
        errors.append(
            f"{key}.distribution: bernoulli p must satisfy 0 <= p <= 1, got {numeric['p']}"
        )
    elif dist_type == "beta":
        if numeric["alpha"] <= 0:
            errors.append(f"{key}.distribution: beta alpha must be > 0, got {numeric['alpha']}")
        if numeric["beta"] <= 0:
            errors.append(f"{key}.distribution: beta beta must be > 0, got {numeric['beta']}")
    elif dist_type in ("pert", "triangular"):
        low, mode, high = numeric["low"], numeric["mode"], numeric["high"]
        if not low <= mode <= high:
            errors.append(
                f"{key}.distribution: {dist_type} requires low <= mode <= high, "
                f"got low={low}, mode={mode}, high={high}"
            )
    elif dist_type in ("lognormal", "shifted_lognormal"):
        if numeric["sigma"] <= 0:
            errors.append(
                f"{key}.distribution: {dist_type} sigma must be > 0, got {numeric['sigma']}"
            )
    elif dist_type == "gamma":
        if numeric["shape"] <= 0:
            errors.append(f"{key}.distribution: gamma shape must be > 0, got {numeric['shape']}")
        if numeric["scale"] <= 0:
            errors.append(f"{key}.distribution: gamma scale must be > 0, got {numeric['scale']}")


def _validate_parameter(key: str, entry: Any, errors: list[str]) -> None:
    if not isinstance(entry, dict):
        errors.append(f"{key}: expected a mapping")
        return

    for unknown in sorted(set(entry) - PARAMETER_FIELDS):
        errors.append(f"{key}.{unknown}: unknown field")
    for missing in sorted(PARAMETER_FIELDS - set(entry)):
        errors.append(f"{key}.{missing}: missing required field")

    value = entry.get("value")
    if value is not None and not _is_number(value):
        errors.append(f"{key}.value: expected a number or null")

    if "unit" in entry and not isinstance(entry["unit"], str):
        errors.append(f"{key}.unit: expected a string")

    if entry.get("distribution") is not None:
        _validate_distribution(key, entry["distribution"], errors)

    source_url = entry.get("source_url")
    if source_url is not None and not isinstance(source_url, str):
        errors.append(f"{key}.source_url: expected a string or null")

    source_type = entry.get("source_type")
    if "source_type" in entry and source_type not in SOURCE_TYPES:
        allowed = ", ".join(sorted(SOURCE_TYPES))
        errors.append(f"{key}.source_type: unknown value {source_type!r} (allowed: {allowed})")

    justification = entry.get("justification")
    if "justification" in entry and (
        not isinstance(justification, str) or not justification.strip()
    ):
        errors.append(f"{key}.justification: must be a non-empty string")

    as_of_raw = entry.get("as_of")
    if as_of_raw is not None and _as_date(as_of_raw) is None:
        errors.append(f"{key}.as_of: expected an ISO date (YYYY-MM-DD) or null")

    status = entry.get("status")
    if "status" not in entry:
        return
    if status not in STATUSES:
        allowed = ", ".join(sorted(STATUSES))
        errors.append(f"{key}.status: unknown value {status!r} (allowed: {allowed})")
        return

    if status == "VERIFIED":
        if source_url is None:
            errors.append(f"{key}: status VERIFIED requires a non-null source_url")
        if as_of_raw is None:
            errors.append(f"{key}: status VERIFIED requires a non-null as_of")
    elif status == "ESTIMATE":
        if source_type != "estimate":
            errors.append(
                f"{key}: status ESTIMATE requires source_type 'estimate', got {source_type!r}"
            )
    elif status == "PLACEHOLDER":
        if value is not None:
            errors.append(f"{key}: status PLACEHOLDER requires value to be null, got {value!r}")


def validate(raw: dict, asset_id: str) -> list[str]:
    """Return every violation in ``raw``, checked against ``asset_id``.

    Pure: performs no filesystem or network access. An empty list means the
    mapping is a valid assumptions file for that asset.
    """
    errors: list[str] = []

    if not isinstance(raw, dict):
        return ["top level: expected a mapping"]

    for unknown in sorted(set(raw) - TOP_LEVEL_KEYS):
        errors.append(f"{unknown}: unknown top-level key")
    for missing in sorted(TOP_LEVEL_KEYS - set(raw)):
        errors.append(f"{missing}: missing required top-level key")

    for key in _STRING_TOP_LEVEL:
        if key in raw and (not isinstance(raw[key], str) or not raw[key].strip()):
            errors.append(f"{key}: expected a non-empty string")

    declared_id = raw.get("asset_id")
    if isinstance(declared_id, str) and declared_id != asset_id:
        errors.append(
            f"asset_id: declared {declared_id!r} but the containing folder is {asset_id!r}; "
            "they must match"
        )

    if "catalyst" in raw:
        _validate_catalyst(raw["catalyst"], errors)

    if "parameters" in raw:
        parameters = raw["parameters"]
        if not isinstance(parameters, dict):
            errors.append("parameters: expected a mapping of param_key -> entry")
        else:
            for key, entry in parameters.items():
                if not isinstance(key, str):
                    errors.append(f"parameters.{key!r}: parameter keys must be strings")
                    continue
                _validate_parameter(key, entry, errors)

    return errors


# --------------------------------------------------------------------------
# Parsing and loading
# --------------------------------------------------------------------------


def _build(raw: dict) -> AssetConfig:
    """Construct an AssetConfig from a mapping already known to be valid."""
    parameters: dict[str, Parameter] = {}
    for key, entry in raw["parameters"].items():
        dist_raw = entry.get("distribution")
        distribution = None
        if dist_raw is not None:
            params = dist_raw.get("params") or {}
            distribution = Distribution(
                type=dist_raw["type"],
                params={name: float(val) for name, val in params.items()},
            )
        value = entry.get("value")
        parameters[key] = Parameter(
            key=key,
            value=None if value is None else float(value),
            unit=entry["unit"],
            distribution=distribution,
            source_url=entry.get("source_url"),
            source_type=entry["source_type"],
            justification=entry["justification"],
            status=entry["status"],
            as_of=_as_date(entry.get("as_of")),
        )

    return AssetConfig(
        asset_id=raw["asset_id"],
        asset_name=raw["asset_name"],
        company=raw["company"],
        ticker=raw["ticker"],
        catalyst=dict(raw["catalyst"]),
        parameters=parameters,
    )


def load_asset_config(asset_id: str, assets_dir: Path = Path("assets")) -> AssetConfig:
    """Load and validate ``<assets_dir>/<asset_id>/assumptions.yaml``.

    Raises:
        ConfigError: listing every violation found, or reporting a missing or
            unparseable file.
    """
    path = Path(assets_dir) / asset_id / "assumptions.yaml"
    if not path.is_file():
        raise ConfigError([f"{path}: assumptions file not found"])

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError([f"{path}: YAML could not be parsed: {exc}"]) from exc

    if raw is None:
        raise ConfigError([f"{path}: file is empty"])
    if not isinstance(raw, dict):
        raise ConfigError([f"{path}: top level must be a mapping"])

    errors = validate(raw, asset_id)
    if errors:
        raise ConfigError([f"{path}: {message}" for message in errors])

    return _build(raw)
