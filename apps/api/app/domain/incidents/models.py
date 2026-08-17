from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IncidentStatus(StrEnum):
    RECEIVED = "RECEIVED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class IncidentCreate(StrictModel):
    description: str = Field(min_length=1, max_length=4000)
    location: str = Field(min_length=1, max_length=200)


class Incident(StrictModel):
    id: str
    reference_code: str
    description: str
    location: str
    status: IncidentStatus
    category: str | None = None
    priority: str | None = None
    assigned_team: str | None = None
    requires_human_review: bool = False
    created_at: datetime
    updated_at: datetime


class IncidentCreated(StrictModel):
    id: str
    reference_code: str
    status: IncidentStatus


class IncidentTracked(StrictModel):
    reference_code: str
    status: IncidentStatus
    location: str
    created_at: datetime
    updated_at: datetime


class StatusUpdate(StrictModel):
    status: IncidentStatus


class IncidentList(StrictModel):
    incidents: list[Incident]
