from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Date,
    DateTime,
    ForeignKey,
    text,
)


class Base(DeclarativeBase):
    pass


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
