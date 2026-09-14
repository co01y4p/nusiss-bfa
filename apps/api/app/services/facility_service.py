from app.domain.facilities.models import BuildingLayout, BuildingLayoutInput
from app.repositories.interfaces.facilities import FacilityLayoutRepository


class FacilityService:
    def __init__(self, repository: FacilityLayoutRepository) -> None:
        self.repository = repository

    def get_layout(self) -> BuildingLayout:
        return BuildingLayout(floors=self.repository.get_layout())

    def replace_layout(self, data: BuildingLayoutInput) -> BuildingLayout:
        return BuildingLayout(floors=self.repository.replace_layout(data.floors))
