from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    DateTime,
    Enum,
    SmallInteger,
    text,
    ForeignKey,
    Integer,
    DECIMAL,
    Date,
)


class Base(DeclarativeBase):
    pass

class Upload(Base):
    __tablename__ = "data_uploads"

    id = Column(BigInteger(), primary_key=True, autoincrement=True)
    site_id = Column(BigInteger(), ForeignKey("sites.id"), nullable=True, index=True)
    file_name = Column(String(50), nullable=False)
    file_path = Column(String(100), nullable=False)
    file_size = Column(String(100), nullable=True)
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    comments = Column(String(20000), nullable=True)
    error_messages = Column(String(1000), nullable=True)
    log_path = Column(String(3000), nullable=True)
    unzipped_path = Column(String(3000), nullable=True)
    status = Column(Enum("Queued", "Parsing", "ParsingComplete", "Error", "SeqError", "Resolved", "SentToNinosPipe", "Imported", name="data_uploads_enum"), nullable=False, server_default="Queued")
    data_type = Column(Enum("Clinical", "Research", name="data_uploads_data_type_enum"), nullable=True)
    progress = Column(SmallInteger(), nullable=True, server_default=text("0"))
    reuploads = Column(SmallInteger(), nullable=True, server_default=text("0"))
    user_id = Column(BigInteger(), ForeignKey("users.id"), nullable=True, index=True)
    user_cwl = Column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<Upload(id={self.id}, file_name='{self.file_name}', file_path='{self.file_path}', status='{self.status}', data_type='{self.data_type}')>"

class Site(Base):
    __tablename__ = "sites"

    id = Column(BigInteger(), primary_key=True, autoincrement=True)
    study_id = Column(BigInteger(), ForeignKey("studies.id"), nullable=True, index=True)
    name = Column(String(50), nullable=False)
    sponsor_site_id = Column(String(100), nullable=True)
    shortname = Column(String(12), nullable=False, unique=True)
    upload_path = Column(String(100), nullable=True)
    country = Column(String(50), nullable=False)
    state_province = Column(String(50), nullable=False)
    city = Column(String(50), nullable=False)
    PI_first_name = Column(String(50), nullable=True)
    PI_last_name = Column(String(50), nullable=True)
    PI_institutional_email = Column(String(150), nullable=True)
    PI_academic_position = Column(String(100), nullable=True)
    PI_telephone_number = Column(String(50), nullable=True)
    expected_sequences = Column(String(200), nullable=False)
    expected_no_participants = Column(BigInteger, nullable=True)
    expected_timepoints = Column(BigInteger, nullable=True)
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    creator_id = Column(BigInteger(), ForeignKey("users.id"), nullable=True, index=True)
    legacy_msmri_site_code = Column(String(10), nullable=True)
    non_uploader = Column(SmallInteger, nullable=False, server_default=text("0"))

    def __repr__(self) -> str:
        return f"<Site(id={self.id}, name='{self.name}', shortname='{self.shortname}', country='{self.country}', city='{self.city}')>"

class Sequence(Base):
    __tablename__ = "sequences"

    id = Column(BigInteger(), primary_key=True, autoincrement=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True, index=True)
    series_description = Column(String(100), nullable=False)
    acquisition_type = Column(String(20), nullable=True)
    repetition_time = Column(DECIMAL(20, 10), nullable=False)
    body_part_examined = Column(String(100), nullable=True)
    scan_id = Column(BigInteger(), ForeignKey("scans.id"), nullable=True, index=True)
    data_upload_id = Column(BigInteger(), ForeignKey("data_uploads.id"), nullable=False, index=True)
    series_number = Column(Integer, nullable=False)
    predicted_sequence_type = Column(BigInteger(), ForeignKey("sequence_types.id"), nullable=True, index=True)
    needs_phillips_rescaling_check = Column(SmallInteger(), nullable=True)
    warning_messages = Column(String(3000), nullable=True)
    error_messages = Column(String(3000), nullable=True)
    QC_comments = Column(String(3000), nullable=True)
    QC_user = Column(BigInteger(), ForeignKey("users.id"), nullable=True, index=True)
    QC_time = Column(DateTime, nullable=True)
    status = Column(Enum(
        "Pending Conversion",
        "Pending QC",
        "Pending PostProcessing",
        "Accepted",
        "Caution",
        "Rejected",
        "Error",
        "ErrorCategorize",
        "Extra",
        "QC not needed",
        name="sequence_status_enum",
    ), nullable=False, server_default="Pending Conversion")
    QC_artifacts = Column(SmallInteger, nullable=True)
    contrast_bolus_agent = Column(String(20), nullable=True)
    random_forest_predicted_sequence_type = Column(BigInteger(), ForeignKey("sequence_types.id"), nullable=True, index=True)
    QC_external_comments = Column(String(3000), nullable=True)
    QC_external_user = Column(BigInteger(), ForeignKey("users.id"), nullable=True)
    QC_external_time = Column(DateTime, nullable=True)
    QC_external_artifacts = Column(SmallInteger, nullable=True)
    
    def __repr__(self) -> str:
        return f"<Sequence(id={self.id}, data_upload_id='{self.data_upload_id}', series_number='{self.series_number}', series_description='{self.series_description}', predicted_sequence_type='{self.predicted_sequence_type}', status='{self.status}', qc_artifacts='{self.QC_artifacts}')>"

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger(), primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=True)
    password = Column(String(255), nullable=True)
    email = Column(String(255), nullable=False)
    type = Column(Enum("user", "admin", "dev", name="users_type_enum"), nullable=False, server_default="user")
    last_login = Column(DateTime, nullable=True)
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    deactivated = Column(SmallInteger, nullable=False, server_default=text("0"))
    token = Column(String(255), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, username={self.username}, "
            f"email={self.email}, type={self.type}, deactivated={self.deactivated})>"
        )
    
class SequenceType(Base):
    __tablename__ = "sequence_types"

    id = Column(BigInteger(), primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    description = Column(String(500), nullable=True)
    category = Column(Enum("clinical", "research", "both", name="sequence_types_category_enum"), nullable=True, server_default="both")

    def __repr__(self) -> str:
        return (
            f"<SequenceType(id={self.id}, name='{self.name}', "
            f"category='{self.category}')>"
        )

class File(Base):
    __tablename__ = "files"

    id = Column(BigInteger(), primary_key=True, autoincrement=True)
    filename = Column(String(150), nullable=False)
    location = Column(String(4096), nullable=False)
    filetype = Column(String(100), nullable=False)
    sequence_id = Column(BigInteger(), ForeignKey("sequences.id"), nullable=True, index=True)
    data_upload_id = Column(BigInteger(), ForeignKey("data_uploads.id"), nullable=True, index=True)
    create_time = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    def __repr__(self) -> str:
        return (
            f"<File(id={self.id}, filename='{self.filename}', "
            f"filetype='{self.filetype}', data_upload_id={self.data_upload_id})>"
        )


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(BigInteger(), primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    site_id = Column(BigInteger(), ForeignKey("sites.id"), nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<Subject(id={self.id}, name='{self.name}')>"


class Scan(Base):
    __tablename__ = "scans"

    id = Column(BigInteger(), primary_key=True, autoincrement=True)
    timepoint = Column(String(50), nullable=False)
    acquisition_date = Column(Date, nullable=False)
    subject_id = Column(BigInteger(), ForeignKey("subjects.id"), nullable=True, index=True)

    def __repr__(self) -> str:
        return (
            f"<Scan(id={self.id}, timepoint='{self.timepoint}', "
            f"acquisition_date='{self.acquisition_date}')>"
        )
