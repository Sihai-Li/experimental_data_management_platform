import uuid
from datetime import datetime
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

POSITIONS = tuple(
    f"{row}_{col}" for row in ("upper", "middle", "lower") for col in ("left", "center", "right")
)
POSITION_SQL = ", ".join(repr(p) for p in POSITIONS)


class Base(DeclarativeBase):
    pass


class IdentityMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class User(IdentityMixin, Base):
    __tablename__ = "app_user"
    issuer: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    is_supervisor: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_user_identity"),)


class Project(IdentityMixin, Base):
    __tablename__ = "project"
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("length(name) > 0", name="ck_project_name"),)


class Membership(Base):
    __tablename__ = "membership"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("role IN ('LAB_MEMBER', 'GUEST')", name="ck_membership_role"),)


class ResearchAnimal(IdentityMixin, Base):
    __tablename__ = "research_animal"
    code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("code ~ '^[A-Za-z]{3}$'", name="ck_animal_code"),)


class RecordingSession(IdentityMixin, Base):
    __tablename__ = "recording_session"
    animal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_animal.id"), nullable=False)
    session_number: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        UniqueConstraint("animal_id", "session_number", name="uq_animal_session"),
        CheckConstraint("session_number BETWEEN 0 AND 999", name="ck_session_number"),
    )


class ImportRecord(IdentityMixin, Base):
    __tablename__ = "import_record"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), nullable=False)
    imported_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False)
    received_filename: Mapped[str] = mapped_column(String, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String, nullable=False)
    contract_version: Mapped[str] = mapped_column(String, nullable=False)
    parser_version: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    staging_key: Mapped[str | None] = mapped_column(String)
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_import_project"),
        CheckConstraint(
            "status IN ('RECEIVED','VALIDATING','IMPORTING','SUCCEEDED','REJECTED','SKIPPED','FAILED')",
            name="ck_import_status",
        ),
        CheckConstraint("sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'", name="ck_import_hash"),
        Index("ix_import_status_started", "status", "started_at"),
    )


class SourceFile(IdentityMixin, Base):
    __tablename__ = "source_file"
    import_record_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    original_file_name: Mapped[str] = mapped_column(String, nullable=False)
    save_file_name: Mapped[str] = mapped_column(String, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    storage_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    contract_version: Mapped[str] = mapped_column(String, nullable=False)
    parser_version: Mapped[str] = mapped_column(String, nullable=False)
    source_structure: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_source_project"),
        ForeignKeyConstraint(
            ["import_record_id", "project_id"], ["import_record.id", "import_record.project_id"]
        ),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_source_hash"),
        CheckConstraint("byte_size > 0", name="ck_source_size"),
    )


class NeuronRecording(IdentityMixin, Base):
    __tablename__ = "neuron_recording"
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recording_session.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), nullable=False, index=True)
    source_file_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, nullable=False)
    neuron_number: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    experiment_type_name: Mapped[str] = mapped_column(String, nullable=False)
    training_phase_name: Mapped[str] = mapped_column(String, nullable=False)
    brain_area_name: Mapped[str] = mapped_column(String, nullable=False)
    experiment_type: Mapped[int] = mapped_column(BigInteger, nullable=False)
    training_phase_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    brain_area_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_interval_us: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["source_file_id", "project_id"], ["source_file.id", "source_file.project_id"]),
        CheckConstraint("trial_count > 0", name="ck_trial_count"),
        CheckConstraint("sample_count = 6001", name="ck_sample_count"),
        CheckConstraint("sample_interval_us = 1000", name="ck_interval"),
    )


class Trial(Base):
    __tablename__ = "trial"
    recording_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("neuron_recording.id"), primary_key=True)
    trial_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    stimulus_position_name: Mapped[str] = mapped_column(String, nullable=False)
    second_stimulus_position_name: Mapped[str] = mapped_column(String, nullable=False)
    is_match_trial: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cue_sample_interval_length: Mapped[float] = mapped_column(Double, nullable=False)
    cue_reward_interval_length: Mapped[float] = mapped_column(Double, nullable=False)
    __table_args__ = (
        CheckConstraint("trial_index >= 1", name="ck_trial_index"),
        CheckConstraint(f"stimulus_position_name IN ({POSITION_SQL})", name="ck_first_position"),
        CheckConstraint(f"second_stimulus_position_name IN ({POSITION_SQL})", name="ck_second_position"),
        CheckConstraint(
            "is_match_trial = (stimulus_position_name = second_stimulus_position_name)", name="ck_match"
        ),
    )
