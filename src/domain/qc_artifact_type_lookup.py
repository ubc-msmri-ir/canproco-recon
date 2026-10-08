import json
import logging

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator, model_validator

from domain.value_objects import normalize_qc_artifact_type

logger = logging.getLogger(__name__)


class CanProCoQCArtifactTypeLookup(BaseModel):
    """One row of the QC comment -> QC artifact type lookup CSV."""

    model_config = ConfigDict(populate_by_name=True)

    qc_comments: str = Field(alias="QC_comments")
    category: str | None = Field(default=None, alias="Clinical/Research")
    sequence_ids: list[PositiveInt] = Field(alias="sequence_ids", min_length=1)
    count: int = Field(alias="count")
    qc_artifact_type: str | None = Field(default=None, alias="QC_artifact_type")

    @field_validator("qc_comments")
    @classmethod
    def require_comment(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("QC_comments must not be empty")
        return v

    @field_validator("category", mode="before")
    @classmethod
    def blank_category_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("sequence_ids", mode="before")
    @classmethod
    def parse_sequence_ids(cls, v):
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("sequence_ids must not be empty")
            try:
                v = json.loads(v)  # "[1, 2, 3]" -> [1, 2, 3]
            except json.JSONDecodeError as e:
                raise ValueError(f"sequence_ids is not a list of integers: {v!r}") from e
        return v

    @field_validator("qc_artifact_type", mode="before")
    @classmethod
    def normalize_artifact_type(cls, v):
        return normalize_qc_artifact_type(v)

    @model_validator(mode="after")
    def warn_on_count_mismatch(self):
        if self.count != len(self.sequence_ids):
            logger.warning(
                "count=%d but %d sequence_ids for QC comment %r (%s)",
                self.count, len(self.sequence_ids), self.qc_comments, self.category,
            )
        return self
