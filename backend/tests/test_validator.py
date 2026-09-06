import hashlib
import json
import os
from pathlib import Path
import numpy as np
import pytest
from scipy.io import loadmat, savemat
from app.mat_validator import parse_file


@pytest.mark.parametrize("compressed", [True, False])
def test_readonly_roundtrip(mat_case, compressed):
    doc, write = mat_case
    path = write(compressed)
    before = path.read_bytes()
    report, parsed = parse_file(path)
    assert report["status"] == "VALID", report
    assert path.read_bytes() == before
    assert report["sha256"] == hashlib.sha256(before).hexdigest()
    np.testing.assert_array_equal(parsed.raster, doc["raster_data"])
    np.testing.assert_array_equal(
        parsed.timing["cue_sample_interval_length"],
        doc["raster_site_info"]["timing_info"]["cue_sample_interval_length"],
    )
    assert report["summary"]["spike_count"] == 1


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("columns", "INVALID_STRUCTURE"),
        ("labels", "INVALID_STRUCTURE"),
        ("match", "MATCH_LABEL_MISMATCH"),
        ("position", "INVALID_VALUE"),
        ("neuron", "IDENTITY_MISMATCH"),
        ("missing", "INVALID_STRUCTURE"),
        ("raster", "INVALID_VALUE"),
        ("complex", "INVALID_STRUCTURE"),
        ("integer", "INVALID_STRUCTURE"),
        ("matrix_vector", "INVALID_STRUCTURE"),
    ],
)
def test_rejections(mat_case, mutation, code):
    doc, write = mat_case
    if mutation == "columns":
        doc["raster_data"] = doc["raster_data"][:, :-1]
    if mutation == "labels":
        doc["raster_labels"]["is_match_trial"] = np.array([1])
    if mutation == "match":
        doc["raster_labels"]["is_match_trial"][1] = 1
    if mutation == "position":
        doc["raster_labels"]["stimulus_position_names"][1] = "outside"
    if mutation == "neuron":
        doc["raster_site_info"]["neuron_number"] = 43
    if mutation == "missing":
        del doc["raster_site_info"]["timing_info"]
    if mutation == "raster":
        doc["raster_data"][1, 9] = np.nan
    if mutation == "complex":
        doc["raster_data"] = doc["raster_data"].astype(complex) + 1j
    if mutation == "integer":
        doc["raster_site_info"]["neuron_number"] = 42.5
    if mutation == "matrix_vector":
        doc["raster_data"] = np.zeros((4, 6001))
        doc["raster_labels"]["is_match_trial"] = np.ones((2, 2))
    report, parsed = parse_file(write())
    assert parsed is None
    assert report["status"] == "REJECTED"
    assert code in {i["code"] for i in report["issues"]}
    if mutation == "raster":
        first = report["issues"][0]
        assert (first["trial_index"], first["column_index"]) == (2, 10)


def test_single_trial_column_vectors_and_warnings(mat_case):
    doc, write = mat_case
    doc["raster_data"] = doc["raster_data"][:1]
    for k, v in doc["raster_labels"].items():
        doc["raster_labels"][k] = v[:1].reshape(1, 1)
    for k in doc["raster_site_info"]["timing_info"]:
        doc["raster_site_info"]["timing_info"][k] = np.array([[np.nan]])
    doc["raster_site_info"]["new_field"] = 5
    report, parsed = parse_file(write())
    assert report["status"] == "VALID", report
    assert parsed.raster.shape == (1, 6001)
    assert np.isnan(parsed.timing["cue_sample_interval_length"][0])
    assert {i["code"] for i in report["issues"]} == {"UNMAPPED_FIELD", "NONFINITE_TIME"}
    json.dumps(report, allow_nan=False)


def test_skip_variant_and_corruption(mat_case):
    _, write = mat_case
    path = write()
    other = path.with_name(path.name.replace("_1_42_", "_2_42_"))
    other.write_bytes(path.read_bytes())
    assert parse_file(other)[0]["status"] == "SKIPPED"
    path.write_bytes(path.read_bytes()[:-12])
    assert parse_file(path)[0]["status"] == "REJECTED"


def test_limits_and_missing(mat_case, monkeypatch):
    import app.mat_validator as validator

    _, write = mat_case
    path = write()
    monkeypatch.setattr(validator, "MAX_EXPANDED_BYTES", 100)
    report, _ = parse_file(path)
    assert report["issues"][0]["code"] == "RESOURCE_LIMIT"
    assert parse_file(path.with_name("absent.mat"))[0]["status"] == "REJECTED"


SAMPLES = [
    ("ADR001_1_3000_SPATIAL_PRE_dorsal_raster_data.mat", 108, 44, 54),
    ("ADR004_1_3007_SPATIAL_PRE_ventral_raster_data.mat", 180, 370, 90),
    ("ELV003_1_1004_SPATIAL_PRE_ventral_raster_data.mat", 144, 4687, 72),
]


@pytest.mark.samples
@pytest.mark.parametrize("name,n,spikes,matches", SAMPLES)
def test_real_samples(name, n, spikes, matches, tmp_path):
    root = Path(os.environ.get("SAMPLE_DATA_DIR", "spatial_data_pre_training"))
    path = root / name
    if not path.exists():
        pytest.skip("Private real sample data is not present")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    report, parsed = parse_file(path)
    assert report["status"] == "VALID", report
    assert report["issues"] == []
    assert parsed.raster.shape == (n, 6001)
    assert report["summary"]["spike_count"] == spikes
    assert report["summary"]["match_trials"] == matches
    assert before == report["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    original = loadmat(path, simplify_cells=True)
    np.testing.assert_array_equal(parsed.raster, original["raster_data"])
    for k, v in parsed.metadata.items():
        assert v == original["raster_site_info"][k]
    for k, v in parsed.labels.items():
        np.testing.assert_array_equal(v, original["raster_labels"][k])
    for k, v in parsed.timing.items():
        np.testing.assert_array_equal(v, original["raster_site_info"]["timing_info"][k])
    # Corrupt only a temporary copy derived from real data.
    original["raster_labels"]["is_match_trial"][0] = 1 - original["raster_labels"]["is_match_trial"][0]
    copy = tmp_path / name
    savemat(copy, {k: v for k, v in original.items() if not k.startswith("__")})
    assert "MATCH_LABEL_MISMATCH" in {i["code"] for i in parse_file(copy)[0]["issues"]}
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_column_vectors(mat_case):
    doc, write = mat_case
    for key, value in doc["raster_labels"].items():
        doc["raster_labels"][key] = value.reshape(-1, 1)
    for key, value in doc["raster_site_info"]["timing_info"].items():
        doc["raster_site_info"]["timing_info"][key] = value.reshape(-1, 1)
    report, parsed = parse_file(write())
    assert report["status"] == "VALID", report
    assert parsed.labels["stimulus_position_names"] == ["upper_left", "middle_center"]


def test_nonvector_with_correct_element_count(mat_case):
    doc, write = mat_case
    doc["raster_data"] = np.zeros((4, 6001))
    for key, value in doc["raster_labels"].items():
        doc["raster_labels"][key] = np.tile(value, 2).reshape(1, 4)
    doc["raster_labels"]["is_match_trial"] = np.ones((2, 2))
    report, _ = parse_file(write())
    assert report["status"] == "REJECTED"
    assert report["issues"][0]["field_path"] == "raster_labels.is_match_trial"


def test_v73_rejected(mat_case):
    _, write = mat_case
    path = write()
    data = bytearray(path.read_bytes())
    data[:10] = b"MATLAB 7.3"
    path.write_bytes(data)
    assert parse_file(path)[0]["issues"][0]["code"] == "UNSUPPORTED_MAT_FORMAT"


def test_cli_json_and_exit_code(mat_case):
    import subprocess
    import sys

    doc, write = mat_case
    doc["raster_labels"]["is_match_trial"][0] = 0
    path = write()
    result = subprocess.run(
        [sys.executable, "-m", "app.mat_validator", str(path)],
        env={**os.environ, "PYTHONPATH": "backend"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)[0]
    assert report["status"] == "REJECTED"
    assert "Traceback" not in result.stderr
