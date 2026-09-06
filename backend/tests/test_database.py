import uuid
import pytest
from test_health import request
from sqlalchemy import insert, inspect
from sqlalchemy.exc import IntegrityError
from app.models import (
    User,
    Project,
    Membership,
    ResearchAnimal,
    RecordingSession,
    ImportRecord,
    SourceFile,
    NeuronRecording,
    Trial,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def graph(pg_engine):
    with pg_engine.connect() as c:
        tx = c.begin()
        ids = {
            k: uuid.uuid4()
            for k in ("user", "project", "other", "animal", "session", "import", "source", "recording")
        }
        rows = [
            (User, dict(id=ids["user"], issuer="test", subject="1")),
            (Project, dict(id=ids["project"], name="Test", created_by=ids["user"])),
            (Project, dict(id=ids["other"], name="Other", created_by=ids["user"])),
            (ResearchAnimal, dict(id=ids["animal"], code="TST")),
            (RecordingSession, dict(id=ids["session"], animal_id=ids["animal"], session_number=1)),
            (
                ImportRecord,
                dict(
                    id=ids["import"],
                    project_id=ids["project"],
                    imported_by=ids["user"],
                    received_filename="test.mat",
                    status="IMPORTING",
                    contract_version="1",
                    parser_version="0.2.0",
                ),
            ),
            (
                SourceFile,
                dict(
                    id=ids["source"],
                    project_id=ids["project"],
                    import_record_id=ids["import"],
                    original_filename="test.mat",
                    original_file_name="test",
                    save_file_name="test",
                    sha256="a" * 64,
                    storage_key="originals/test/source.mat",
                    byte_size=10,
                    contract_version="1",
                    parser_version="0.2.0",
                ),
            ),
            (
                NeuronRecording,
                dict(
                    id=ids["recording"],
                    project_id=ids["project"],
                    session_id=ids["session"],
                    source_file_id=ids["source"],
                    neuron_number=42,
                    experiment_type_name="SPATIAL",
                    training_phase_name="PRE",
                    brain_area_name="dorsal",
                    experiment_type=1,
                    training_phase_number=1,
                    brain_area_number=1,
                    trial_count=1,
                    sample_count=6001,
                    sample_interval_us=1000,
                ),
            ),
        ]
        for model, row in rows:
            c.execute(insert(model).values(**row))
        yield c, ids, dict(rows[-1][1])
        tx.rollback()


@pytest.mark.parametrize("case", ["session", "neuron", "hash", "project", "orphan", "match", "role"])
def test_database_rejects_invalid_writes(graph, case):
    c, ids, recording = graph
    if case == "session":
        stmt = insert(RecordingSession).values(animal_id=ids["animal"], session_number=1)
    if case in ("neuron", "hash"):
        new_import, new_source = uuid.uuid4(), uuid.uuid4()
        c.execute(
            insert(ImportRecord).values(
                id=new_import,
                project_id=ids["project"],
                imported_by=ids["user"],
                received_filename="other.mat",
                status="IMPORTING",
                contract_version="1",
                parser_version="0.2.0",
            )
        )
        source_values = dict(
            id=new_source,
            project_id=ids["project"],
            import_record_id=new_import,
            original_filename="other.mat",
            original_file_name="other",
            save_file_name="other",
            sha256="b" * 64,
            storage_key="originals/other/source.mat",
            byte_size=20,
            contract_version="1",
            parser_version="0.2.0",
        )
        if case == "hash":
            stmt = insert(SourceFile).values(**{**source_values, "sha256": "a" * 64})
        else:
            c.execute(insert(SourceFile).values(**source_values))
            stmt = insert(NeuronRecording).values(
                **{**recording, "id": uuid.uuid4(), "source_file_id": new_source}
            )
    if case == "project":
        stmt = (
            NeuronRecording.__table__.update()
            .where(NeuronRecording.id == ids["recording"])
            .values(project_id=ids["other"])
        )
    if case == "orphan":
        stmt = insert(RecordingSession).values(animal_id=uuid.uuid4(), session_number=2)
    if case == "match":
        stmt = insert(Trial).values(
            recording_id=ids["recording"],
            trial_index=1,
            stimulus_position_name="upper_left",
            second_stimulus_position_name="upper_left",
            is_match_trial=False,
            cue_sample_interval_length=2.01755,
            cue_reward_interval_length=4.05175,
        )
    if case == "role":
        stmt = insert(Membership).values(project_id=ids["project"], user_id=ids["user"], role="SUPERVISOR")
    with pytest.raises(IntegrityError) as caught:
        with c.begin_nested():
            c.execute(stmt)
    if case == "hash":
        assert caught.value.orig.diag.constraint_name == "source_file_sha256_key"
    if case == "neuron":
        assert caught.value.orig.diag.constraint_name == "neuron_recording_neuron_number_key"


def test_precision_and_schema(graph, pg_engine):
    c, ids, _ = graph
    c.execute(
        insert(Trial).values(
            recording_id=ids["recording"],
            trial_index=1,
            stimulus_position_name="upper_left",
            second_stimulus_position_name="upper_left",
            is_match_trial=True,
            cue_sample_interval_length=2.01755,
            cue_reward_interval_length=4.05175,
        )
    )
    row = c.exec_driver_sql("SELECT cue_sample_interval_length, cue_reward_interval_length FROM trial").one()
    assert tuple(row) == (2.01755, 4.05175)
    inspector = inspect(pg_engine)
    assert {"trial", "membership", "source_file", "neuron_recording"} <= set(inspector.get_table_names())
    assert any(
        x["column_names"] == ["neuron_number"] for x in inspector.get_unique_constraints("neuron_recording")
    )
    assert any(x["column_names"] == ["sha256"] for x in inspector.get_unique_constraints("source_file"))


def test_readiness(pg_engine, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "get_engine", lambda: pg_engine)
    assert request("/api/health/ready").json()["schema_revision"] == "0001"
