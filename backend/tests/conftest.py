import os
from pathlib import Path
import numpy as np
import pytest
from scipy.io import savemat


@pytest.fixture
def mat_case(tmp_path):
    # Tiny in-memory format fixture for unit tests, never database seed data.
    name = "TST001_1_42_SPATIAL_PRE_dorsal_raster_data.mat"
    doc = {
        "raster_data": np.zeros((2, 6001), dtype=np.float64),
        "raster_labels": {
            "stimulus_position_names": np.array(["upper_left", "middle_center"], dtype=object),
            "second_stimulus_position_names": np.array(["upper_left", "lower_right"], dtype=object),
            "is_match_trial": np.array([1, 0]),
        },
        "raster_site_info": {
            "original_file_name": "TST001_1_42",
            "save_file_name": name[:-4],
            "neuron_number": 42,
            "experiment_type_name": "SPATIAL",
            "experiment_type": 1,
            "training_phase_name": "PRE",
            "training_phase_number": 1,
            "brain_area_name": "dorsal",
            "brain_area_number": 1,
            "timing_info": {
                "cue_sample_interval_length": np.array([2.01755, 2.034225]),
                "cue_reward_interval_length": np.array([4.05175, 4.068425]),
            },
        },
    }
    doc["raster_data"][0, 13] = 1

    def write(compressed=True):
        path = tmp_path / name
        savemat(path, doc, do_compression=compressed)
        return path

    return doc, write


@pytest.fixture(scope="session")
def pg_engine():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect
    from app.config import get_settings

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; use an isolated empty PostgreSQL database")
    engine = create_engine(url)
    if engine.dialect.name != "postgresql":
        pytest.fail("Integration tests require PostgreSQL")
    if inspect(engine).get_table_names():
        pytest.fail("Refusing to run migration lifecycle tests on a nonempty database")
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        command.upgrade(config, "head")
        command.check(config)
        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
        command.upgrade(config, "head")
        yield engine
    finally:
        # Only the initially empty, explicitly designated test database is touched.
        command.downgrade(config, "base")
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        engine.dispose()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
