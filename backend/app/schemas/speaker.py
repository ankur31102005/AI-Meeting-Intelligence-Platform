"""Speaker request/response contracts."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class SpeakerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    diarization_label: str          # immutable machine label ("SPEAKER_00")
    display_name: str | None        # human-assigned name, if renamed
    label: str                      # computed: display_name or diarization_label


class SpeakerRenameRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
