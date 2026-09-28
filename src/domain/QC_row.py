import json
from pydantic import BaseModel, ConfigDict, field_validator

ARTIFACT_DESCRIPTION = {
    "1": "Poor SNR",
    "2": "Magnetic Susceptibility",
    "3": "Motion: Ringing",
    "4": "Motion: Ghosting",
    "5": "Zipper",
    "6": "Wraparound",
    "7": "Geometric Distortion (DTI-only)",
    "8": "Other (comment required)",
}

ARTIFACT = {
    1 : "Yes",
    0 : "No",
}

class QCRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_name: str
    timepoint: str
    sequence_id: int
    sequence_name: str | None = None
    body_part_examined: str | None = None
    predicted_sequence_type: str | None = None
    sequence_status: str
    sequence_qc_artifact: str | None = None
    sequence_qc_artifact_types: list[str] = []
    sequence_qc_comments: str | None = None
    upload_file_path: str

    @field_validator("sequence_qc_artifact", mode="before")
    @classmethod
    def decode_artifact(cls, v):
        if v is None or (v != 1 and v != 0):
            return None
        if isinstance(v, int):
            try:
                return ARTIFACT[v]
            except KeyError as e:
                raise ValueError(f"Unknown artifact code: {e}") from e
    
    @field_validator("sequence_qc_artifact_types", mode="before")
    @classmethod
    def decode_artifact_types(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, str):
            v = json.loads(v)  # '["2", "3"]' -> ["2", "3"]
        try:
            return [ARTIFACT_DESCRIPTION[str(item)] for item in v]
        except KeyError as e:
            raise ValueError(f"Unknown artifact code: {e}") from e