from typing import Protocol

from app.domain.facilities.models import Floor, FloorInput


class FacilityLayoutRepository(Protocol):
    def get_layout(self) -> list[Floor]: ...

    def replace_layout(self, floors: list[FloorInput]) -> list[Floor]: ...
