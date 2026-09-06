"""Read-only, bounded MATLAB level-5 parser. No database writes or data repairs."""

import argparse
import hashlib
import io
import json
import re
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.io import loadmat, whosmat

CONTRACT_VERSION = "1"
PARSER_VERSION = "0.2.0"
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_ELEMENTS = 12_000_000
POSITIONS = {f"{a}_{b}" for a in ("upper", "middle", "lower") for b in ("left", "center", "right")}
NAME = re.compile(
    r"^(?P<animal>[A-Za-z]{3})(?P<session>[0-9]{3})_(?P<variant>[0-9]+)_(?P<neuron>[0-9]+)_(?P<suffix>.+)_raster_data\.mat$"
)
LABELS = {"stimulus_position_names", "second_stimulus_position_names", "is_match_trial"}
TIMES = {"cue_sample_interval_length", "cue_reward_interval_length"}
NAMES = {
    "original_file_name",
    "save_file_name",
    "experiment_type_name",
    "training_phase_name",
    "brain_area_name",
}
CODES = {"neuron_number", "experiment_type", "training_phase_number", "brain_area_number"}


@dataclass
class ParsedRecording:
    animal: str
    session_number: int
    metadata: dict
    raster: np.ndarray
    labels: dict
    timing: dict
    source_structure: list


class Invalid(Exception):
    def __init__(self, code, path, message):
        self.code, self.path, self.message = code, path, message


def _bounded_level5(data):
    # Bound expanded MAT elements before SciPy allocates arrays. v7.3/HDF5 is deliberately unsupported.
    if len(data) < 128 or data.startswith(b"MATLAB 7.3") or data[126:128] not in (b"IM", b"MI"):
        raise Invalid(
            "UNSUPPORTED_MAT_FORMAT", "$", "Only MATLAB level-5 (v5/v6/v7â€“7.2) files are supported"
        )
    endian = "<" if data[126:128] == b"IM" else ">"
    offset, total = 128, 0
    while offset < len(data):
        if len(data) - offset < 8:
            raise Invalid("INVALID_FILE", "$", "Truncated MAT element")
        kind, size = struct.unpack_from(endian + "II", data, offset)
        end = offset + 8 + size
        if end > len(data):
            raise Invalid("INVALID_FILE", "$", "Truncated MAT payload")
        if kind == 15:
            decoder = zlib.decompressobj()
            expanded = decoder.decompress(data[offset + 8 : end], MAX_EXPANDED_BYTES - total + 1)
            total += len(expanded)
            if total > MAX_EXPANDED_BYTES or decoder.unconsumed_tail:
                raise Invalid("RESOURCE_LIMIT", "$", "Expanded MAT exceeds 256 MiB")
            if not decoder.eof or decoder.unused_data:
                raise Invalid("INVALID_FILE", "$", "Invalid compressed MAT element")
            offset = end  # Compressed level-5 elements do not use 8-byte padding.
        elif kind == 14:
            total += size
            offset = end + (-size % 8)
        else:
            raise Invalid("INVALID_FILE", "$", "Unexpected top-level MAT element")
        if total > MAX_EXPANDED_BYTES:
            raise Invalid("RESOURCE_LIMIT", "$", "Expanded MAT exceeds 256 MiB")


def parse_file(path: Path):
    path = Path(path)
    report = {
        "contract_version": CONTRACT_VERSION,
        "parser_version": PARSER_VERSION,
        "status": "REJECTED",
        "filename": path.name,
        "sha256": None,
        "identity": None,
        "trial_count": None,
        "issues": [],
    }

    def issue(code, field, message, severity="error", trial=None, column=None):
        value = {"code": code, "severity": severity, "field_path": field, "message": message}
        if trial is not None:
            value["trial_index"] = int(trial)
        if column is not None:
            value["column_index"] = int(column)
        report["issues"].append(value)

    def fail(field, message):
        raise Invalid("INVALID_STRUCTURE", field, message)

    def fields(value, field, required):
        if not isinstance(value, np.ndarray) or value.size != 1:
            fail(field, "Expected one MATLAB struct")
        value = value.item()
        actual = getattr(value, "_fieldnames", None)
        if actual is None:
            fail(field, "Expected MATLAB struct")
        for missing in sorted(required - set(actual)):
            fail(field + "." + missing, "Required field missing")
        for extra in sorted(set(actual) - required):
            issue("UNMAPPED_FIELD", field + "." + extra, "Preserved only in original MAT", "warning")
        return {key: getattr(value, key) for key in required}

    def string(value, field):
        while isinstance(value, np.ndarray) and value.dtype == object and value.size == 1:
            value = value.item()
        if isinstance(value, str) and value:
            return value
        if isinstance(value, np.ndarray) and value.dtype.kind in "US" and value.size == 1:
            result = str(value.item())
            if result:
                return result
        fail(field, "Expected one nonempty string")

    def vector(value, field, count):
        if (
            not isinstance(value, np.ndarray)
            or value.ndim != 2
            or 1 not in value.shape
            or value.size != count
        ):
            fail(field, f"Expected row or column vector with {count} elements")
        return value.reshape(-1)

    def real(value, field):
        if not isinstance(value, np.ndarray) or value.dtype.kind not in "buif":
            fail(field, "Expected real numeric values")
        return value

    try:
        with path.open("rb") as source:
            data = source.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise Invalid("RESOURCE_LIMIT", "$", "File exceeds 32 MiB")
        report["sha256"] = hashlib.sha256(data).hexdigest()
        match = NAME.fullmatch(path.name)
        if match is None:
            raise Invalid("INVALID_FILENAME", "$filename", "Expected AAA000_1_neuron_names_raster_data.mat")
        if match["variant"] != "1":
            report["status"] = "SKIPPED"
            issue("SKIPPED_UNSUPPORTED_VARIANT", "$filename", "Only variant 1 is supported", "info")
            return report, None
        animal, session, neuron = match["animal"], int(match["session"]), int(match["neuron"])
        report["identity"] = {"animal": animal, "session_number": session, "neuron_number": neuron}
        _bounded_level5(data)
        info = whosmat(io.BytesIO(data))
        raster_info = [v for v in info if v[0] == "raster_data"]
        if len({v[0] for v in info}) != len(info):
            fail("$", "Duplicate top-level variable names")
        if not raster_info:
            fail("raster_data", "Required variable missing")
        shape = raster_info[0][1]
        if len(shape) != 2 or shape[0] < 1 or shape[1] != 6001:
            fail("raster_data", "Expected N x 6001 matrix with N > 0")
        if shape[0] * shape[1] > MAX_ELEMENTS:
            raise Invalid("RESOURCE_LIMIT", "raster_data", "Raster exceeds 12 million elements")
        doc = loadmat(io.BytesIO(data), struct_as_record=False, squeeze_me=False, mat_dtype=False)
        expected = {"raster_data", "raster_labels", "raster_site_info"}
        for missing in expected - doc.keys():
            fail(missing, "Required variable missing")
        for extra in sorted(set(doc) - expected - {"__header__", "__version__", "__globals__"}):
            issue("UNMAPPED_FIELD", extra, "Preserved only in original MAT", "warning")
        raster = real(doc["raster_data"], "raster_data")
        if raster.shape != shape:
            fail("raster_data", "Unexpected decoded raster shape")
        n = shape[0]
        report["trial_count"] = n
        invalid = ~((raster == 0) | (raster == 1))
        if invalid.any():
            row, col = np.unravel_index(int(np.argmax(invalid)), invalid.shape)
            issue(
                "INVALID_VALUE",
                "raster_data",
                "Only 0 and 1 are allowed (first invalid value)",
                trial=row + 1,
                column=col + 1,
            )
        site = fields(doc["raster_site_info"], "raster_site_info", NAMES | CODES | {"timing_info"})
        metadata = {k: string(site[k], "raster_site_info." + k) for k in NAMES}
        for key in sorted(CODES):
            a = real(site[key], "raster_site_info." + key)
            if a.size != 1:
                fail("raster_site_info." + key, "Expected integer-valued scalar")
            v = a.item()
            if not np.isfinite(v) or int(v) != v or not -(2**63) <= int(v) < 2**63:
                fail("raster_site_info." + key, "Expected finite signed 64-bit integer value")
            metadata[key] = int(v)
        prefix = f"{animal}{match['session']}_1_{match['neuron']}"
        reconstructed = f"{prefix}_{metadata['experiment_type_name']}_{metadata['training_phase_name']}_{metadata['brain_area_name']}_raster_data"
        checks = {"neuron_number": neuron, "original_file_name": prefix, "save_file_name": path.stem}
        for key, expected_value in checks.items():
            if metadata[key] != expected_value:
                issue(
                    "IDENTITY_MISMATCH", "raster_site_info." + key, "Filename and internal identity disagree"
                )
        if reconstructed != path.stem:
            issue("IDENTITY_MISMATCH", "$filename", "Filename classifications disagree with internal names")
        raw_labels = fields(doc["raster_labels"], "raster_labels", LABELS)
        labels = {}
        for key in sorted(LABELS - {"is_match_trial"}):
            labels[key] = [
                string(v, f"raster_labels.{key}[{i + 1}]")
                for i, v in enumerate(vector(raw_labels[key], "raster_labels." + key, n))
            ]
            for i, value in enumerate(labels[key]):
                if value not in POSITIONS:
                    issue("INVALID_VALUE", "raster_labels." + key, "Unknown visual cue position", trial=i + 1)
        matches = real(
            vector(raw_labels["is_match_trial"], "raster_labels.is_match_trial", n),
            "raster_labels.is_match_trial",
        )
        labels["is_match_trial"] = matches
        for i, value in enumerate(matches):
            if value not in (0, 1):
                issue("INVALID_VALUE", "raster_labels.is_match_trial", "Expected 0 or 1", trial=i + 1)
            elif bool(value) != (
                labels["stimulus_position_names"][i] == labels["second_stimulus_position_names"][i]
            ):
                issue(
                    "MATCH_LABEL_MISMATCH",
                    "raster_labels.is_match_trial",
                    "Visual cue positions and match label disagree",
                    trial=i + 1,
                )
        raw_timing = fields(site["timing_info"], "raster_site_info.timing_info", TIMES)
        timing = {}
        for key in sorted(TIMES):
            field = "raster_site_info.timing_info." + key
            timing[key] = real(vector(raw_timing[key], field, n), field)
            for i in np.flatnonzero(~np.isfinite(timing[key])):
                issue(
                    "NONFINITE_TIME",
                    field,
                    "Nonfinite time retained; unit and meaning unconfirmed",
                    "warning",
                    trial=i + 1,
                )
        structure = [{"name": name, "shape": list(dims), "matlab_class": cls} for name, dims, cls in info]
        report["source_structure"] = structure
        report["metadata"] = metadata
        report["summary"] = {
            "sample_count": 6001,
            "sample_interval_us": 1000,
            "spike_count": int(np.count_nonzero(raster == 1)),
            "match_trials": int(np.count_nonzero(matches == 1)),
            "non_match_trials": int(np.count_nonzero(matches == 0)),
        }
        if any(v["severity"] == "error" for v in report["issues"]):
            return report, None
        report["status"] = "VALID"
        return report, ParsedRecording(animal, session, metadata, raster, labels, timing, structure)
    except Invalid as error:
        issue(error.code, error.path, error.message)
    except (OSError, ValueError, TypeError, IndexError, OverflowError, zlib.error) as error:
        issue("INVALID_FILE", "$", f"Unable to parse file ({type(error).__name__})")
    return report, None


def main():
    parser = argparse.ArgumentParser(
        description="Validate MAT files without modifying files or writing a database"
    )
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    reports = [parse_file(path)[0] for path in args.files]
    print(json.dumps(reports, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if any(report["status"] == "REJECTED" for report in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
