"""Tests for the assumptions-file schema and loader.

No network access and no model mathematics: these tests only read fixture files
from disk and exercise pure validation logic.
"""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path

import pytest
import yaml

from catalyst_rnpv.config import load_asset_config, validate
from catalyst_rnpv.schema import AssetConfig, ConfigError, Distribution

FIXTURES = Path(__file__).parent / "fixtures"


def _install(tmp_path: Path, fixture: str, asset_id: str) -> Path:
    """Copy a fixture into a tmp assets/<asset_id>/ folder; return the assets dir."""
    assets_dir = tmp_path / "assets"
    (assets_dir / asset_id).mkdir(parents=True)
    shutil.copyfile(FIXTURES / fixture, assets_dir / asset_id / "assumptions.yaml")
    return assets_dir


# --------------------------------------------------------------------------
# 1. The valid file loads and round-trips.
# --------------------------------------------------------------------------


def test_valid_minimal_loads_and_round_trips(tmp_path: Path) -> None:
    assets_dir = _install(tmp_path, "valid_minimal.yaml", "test_asset")

    cfg = load_asset_config("test_asset", assets_dir=assets_dir)

    assert isinstance(cfg, AssetConfig)
    assert cfg.asset_id == "test_asset"
    assert cfg.asset_name == "Test Asset"
    assert cfg.company == "Test Company, Inc."
    assert cfg.ticker == "TEST"
    assert cfg.catalyst["trial_id"] == "NCT00000000"
    assert cfg.catalyst["guided_date"] == "1H 2099"

    entry = cfg.param("fixture_verified_fraction")
    assert entry.key == "fixture_verified_fraction"
    assert entry.value == pytest.approx(0.5)
    assert entry.unit == "fraction"
    assert entry.distribution == Distribution(type="beta", params={"alpha": 2.0, "beta": 3.0})
    assert entry.source_url == "https://example.invalid/fixture-verified"
    assert entry.source_type == "publication"
    assert entry.justification == "fixture entry exercising a fully VERIFIED parameter"
    assert entry.status == "VERIFIED"
    assert entry.as_of == datetime.date(2026, 1, 15)

    nulls = cfg.param("fixture_estimated_count")
    assert nulls.source_url is None
    assert nulls.as_of is None

    assert set(cfg.parameters) == {
        "fixture_verified_fraction",
        "fixture_estimated_count",
        "fixture_unverified_probability",
        "fixture_placeholder",
    }


def test_value_returns_floats(tmp_path: Path) -> None:
    assets_dir = _install(tmp_path, "valid_minimal.yaml", "test_asset")
    cfg = load_asset_config("test_asset", assets_dir=assets_dir)

    for key in ("fixture_verified_fraction", "fixture_estimated_count"):
        got = cfg.value(key)
        assert isinstance(got, float)

    assert cfg.value("fixture_verified_fraction") == pytest.approx(0.5)
    assert cfg.value("fixture_estimated_count") == pytest.approx(1234.0)


def test_param_unknown_key_raises_helpful_key_error(tmp_path: Path) -> None:
    assets_dir = _install(tmp_path, "valid_minimal.yaml", "test_asset")
    cfg = load_asset_config("test_asset", assets_dir=assets_dir)

    with pytest.raises(KeyError) as excinfo:
        cfg.param("no_such_parameter")

    message = str(excinfo.value)
    assert "no_such_parameter" in message
    assert "fixture_verified_fraction" in message


# --------------------------------------------------------------------------
# 2. Analytically known case: exactly three violations.
# --------------------------------------------------------------------------


def test_three_known_errors_are_found_exactly() -> None:
    raw = yaml.safe_load((FIXTURES / "three_known_errors.yaml").read_text(encoding="utf-8"))

    errors = validate(raw, "test_errors")

    assert len(errors) == 3, f"expected exactly 3 violations, got {len(errors)}: {errors}"

    joined = "\n".join(errors)
    for key in ("bad_verified_no_url", "bad_triangular_order", "bad_bernoulli_p"):
        assert sum(key in message for message in errors) == 1, (
            f"expected exactly one message naming {key}, got: {errors}"
        )
    assert "control_valid" not in joined

    by_key = {
        key: next(m for m in errors if key in m)
        for key in ("bad_verified_no_url", "bad_triangular_order", "bad_bernoulli_p")
    }
    assert "source_url" in by_key["bad_verified_no_url"]
    assert "VERIFIED" in by_key["bad_verified_no_url"]
    assert "triangular" in by_key["bad_triangular_order"]
    assert "bernoulli" in by_key["bad_bernoulli_p"]


def test_three_known_errors_file_fails_to_load(tmp_path: Path) -> None:
    assets_dir = _install(tmp_path, "three_known_errors.yaml", "test_errors")

    with pytest.raises(ConfigError) as excinfo:
        load_asset_config("test_errors", assets_dir=assets_dir)

    assert len(excinfo.value.errors) == 3


# --------------------------------------------------------------------------
# 3. .value() on a PLACEHOLDER raises ConfigError.
# --------------------------------------------------------------------------


def test_value_on_placeholder_raises_config_error(tmp_path: Path) -> None:
    assets_dir = _install(tmp_path, "valid_minimal.yaml", "test_asset")
    cfg = load_asset_config("test_asset", assets_dir=assets_dir)

    assert cfg.param("fixture_placeholder").status == "PLACEHOLDER"

    with pytest.raises(ConfigError) as excinfo:
        cfg.value("fixture_placeholder")

    assert excinfo.value.errors
    assert any("fixture_placeholder" in message for message in excinfo.value.errors)
    assert any("PLACEHOLDER" in message for message in excinfo.value.errors)


# --------------------------------------------------------------------------
# 4. asset_id must match the containing folder name.
# --------------------------------------------------------------------------


def test_asset_id_mismatch_fails_to_load(tmp_path: Path) -> None:
    assets_dir = _install(tmp_path, "valid_minimal.yaml", "wrong_folder_name")

    with pytest.raises(ConfigError) as excinfo:
        load_asset_config("wrong_folder_name", assets_dir=assets_dir)

    messages = excinfo.value.errors
    assert len(messages) == 1
    assert "asset_id" in messages[0]
    assert "test_asset" in messages[0]
    assert "wrong_folder_name" in messages[0]


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_asset_config("does_not_exist", assets_dir=tmp_path / "assets")

    assert len(excinfo.value.errors) == 1
    assert "not found" in excinfo.value.errors[0]


# --------------------------------------------------------------------------
# Validator unit checks on the remaining rules.
# --------------------------------------------------------------------------


def _base_raw() -> dict:
    return yaml.safe_load((FIXTURES / "valid_minimal.yaml").read_text(encoding="utf-8"))


def test_valid_minimal_has_no_violations() -> None:
    assert validate(_base_raw(), "test_asset") == []


def test_unknown_top_level_key_is_an_error() -> None:
    raw = _base_raw()
    raw["extra_section"] = {}

    errors = validate(raw, "test_asset")

    assert len(errors) == 1
    assert "extra_section" in errors[0]


def test_unknown_entry_field_is_an_error() -> None:
    raw = _base_raw()
    raw["parameters"]["fixture_placeholder"]["notes"] = "not a schema field"

    errors = validate(raw, "test_asset")

    assert len(errors) == 1
    assert "fixture_placeholder.notes" in errors[0]


def test_unknown_distribution_type_is_an_error() -> None:
    raw = _base_raw()
    raw["parameters"]["fixture_estimated_count"]["distribution"] = {
        "type": "weibull",
        "params": {"k": 1.0},
    }

    errors = validate(raw, "test_asset")

    assert len(errors) == 1
    assert "weibull" in errors[0]


@pytest.mark.parametrize("field", ["source_type", "status"])
def test_unknown_enum_value_is_an_error(field: str) -> None:
    raw = _base_raw()
    raw["parameters"]["fixture_placeholder"][field] = "not_a_real_value"

    errors = validate(raw, "test_asset")

    assert any(field in message for message in errors)


def test_estimate_status_requires_estimate_source_type() -> None:
    raw = _base_raw()
    raw["parameters"]["fixture_estimated_count"]["source_type"] = "publication"

    errors = validate(raw, "test_asset")

    assert len(errors) == 1
    assert "fixture_estimated_count" in errors[0]
    assert "ESTIMATE" in errors[0]


def test_placeholder_with_a_value_is_an_error() -> None:
    raw = _base_raw()
    raw["parameters"]["fixture_placeholder"]["value"] = 42.0

    errors = validate(raw, "test_asset")

    assert len(errors) == 1
    assert "PLACEHOLDER" in errors[0]


def test_empty_justification_is_an_error() -> None:
    raw = _base_raw()
    raw["parameters"]["fixture_placeholder"]["justification"] = "   "

    errors = validate(raw, "test_asset")

    assert len(errors) == 1
    assert "justification" in errors[0]


@pytest.mark.parametrize(
    ("dist", "needle"),
    [
        ({"type": "beta", "params": {"alpha": 0, "beta": 1}}, "alpha"),
        ({"type": "beta", "params": {"alpha": 1, "beta": -1}}, "beta"),
        ({"type": "pert", "params": {"low": 1, "mode": 2, "high": 1.5}}, "pert"),
        ({"type": "lognormal", "params": {"mu": 0.0, "sigma": 0.0}}, "sigma"),
        (
            {"type": "shifted_lognormal", "params": {"shift": 1.0, "mu": 0.0, "sigma": -1.0}},
            "sigma",
        ),
        ({"type": "gamma", "params": {"shape": 0.0, "scale": 1.0}}, "shape"),
        ({"type": "gamma", "params": {"shape": 1.0, "scale": 0.0}}, "scale"),
    ],
)
def test_distribution_range_rules(dist: dict, needle: str) -> None:
    raw = _base_raw()
    raw["parameters"]["fixture_estimated_count"]["distribution"] = dist

    errors = validate(raw, "test_asset")

    assert len(errors) == 1
    assert "fixture_estimated_count" in errors[0]
    assert needle in errors[0]


def test_missing_distribution_param_is_an_error() -> None:
    raw = _base_raw()
    raw["parameters"]["fixture_estimated_count"]["distribution"] = {
        "type": "pert",
        "params": {"low": 1, "mode": 2},
    }

    errors = validate(raw, "test_asset")

    assert len(errors) == 1
    assert "high" in errors[0]


def test_point_distribution_takes_no_params() -> None:
    raw = _base_raw()
    raw["parameters"]["fixture_estimated_count"]["distribution"] = {"type": "point", "params": {}}

    assert validate(raw, "test_asset") == []


def test_validator_collects_every_violation_at_once() -> None:
    raw = _base_raw()
    raw["parameters"]["fixture_placeholder"]["value"] = 1.0
    raw["parameters"]["fixture_placeholder"]["justification"] = ""
    raw["parameters"]["fixture_verified_fraction"]["as_of"] = None
    raw["unexpected"] = 1

    errors = validate(raw, "test_asset")

    assert len(errors) == 4


# --------------------------------------------------------------------------
# The shipped asset files must themselves validate.
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("asset_id", ["_template", "rnac_descartes08"])
def test_shipped_assets_validate(asset_id: str) -> None:
    cfg = load_asset_config(asset_id, assets_dir=REPO_ROOT / "assets")

    assert cfg.asset_id == asset_id
    assert cfg.parameters, "asset declares no parameters"
    for key, entry in cfg.parameters.items():
        assert entry.status == "PLACEHOLDER", f"{key} is not a placeholder"
        assert entry.value is None, f"{key} carries a value before sourcing"
        assert entry.distribution is None, f"{key} carries a distribution before sourcing"


def test_descartes08_catalyst_metadata() -> None:
    cfg = load_asset_config("rnac_descartes08", assets_dir=REPO_ROOT / "assets")

    assert cfg.company == "Cartesian Therapeutics"
    assert cfg.ticker == "RNAC"
    assert cfg.catalyst["trial_id"] == "NCT06799247"
    assert cfg.catalyst["guided_date"] == "1Q 2027"
