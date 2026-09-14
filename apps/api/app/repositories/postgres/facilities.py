from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import FacilityModel, FloorModel
from app.domain.facilities.models import Facility, Floor, FloorInput


def _to_domain(row: FloorModel) -> Floor:
    return Floor(
        id=row.id,
        name=row.name,
        facilities=[
            Facility(id=facility.id, name=facility.name, category=facility.category)
            for facility in row.facilities
        ],
    )


class SqlAlchemyFacilityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_layout(self) -> list[Floor]:
        rows = self.session.scalars(select(FloorModel).order_by(FloorModel.sort_order)).all()
        return [_to_domain(row) for row in rows]

    def replace_layout(self, floors: list[FloorInput]) -> list[Floor]:
        self.session.query(FacilityModel).delete()
        self.session.query(FloorModel).delete()
        self.session.flush()

        for floor_index, floor_input in enumerate(floors):
            floor_row = FloorModel(name=floor_input.name.strip(), sort_order=floor_index)
            floor_row.facilities = [
                FacilityModel(
                    name=facility_input.name.strip(),
                    category=facility_input.category.value,
                    sort_order=facility_index,
                )
                for facility_index, facility_input in enumerate(floor_input.facilities)
            ]
            self.session.add(floor_row)

        self.session.commit()
        return self.get_layout()
