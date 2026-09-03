from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FacilityCategory(StrEnum):
    HVAC = "HVAC"
    LIFT = "LIFT"
    ELECTRICAL = "ELECTRICAL"
    PLUMBING = "PLUMBING"
    ACCESS = "ACCESS"
    GENERAL = "GENERAL"


class FacilityInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    category: FacilityCategory = FacilityCategory.GENERAL


class FloorInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    facilities: list[FacilityInput] = Field(default_factory=list, max_length=100)


class BuildingLayoutInput(StrictModel):
    floors: list[FloorInput] = Field(default_factory=list, max_length=200)


class Facility(StrictModel):
    id: str
    name: str
    category: FacilityCategory


class Floor(StrictModel):
    id: str
    name: str
    facilities: list[Facility]


class BuildingLayout(StrictModel):
    floors: list[Floor]
