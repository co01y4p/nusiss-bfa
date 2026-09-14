from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.facilities.models import BuildingLayout, BuildingLayoutInput
from app.repositories.postgres.facilities import SqlAlchemyFacilityRepository
from app.security.authentication import CurrentUser, require_manager
from app.services.facility_service import FacilityService

router = APIRouter(prefix="/facilities", tags=["facilities"])


def repository(db: Session) -> SqlAlchemyFacilityRepository:
    return SqlAlchemyFacilityRepository(db)


@router.get("/layout", response_model=BuildingLayout)
def get_layout(db: Annotated[Session, Depends(get_db)]) -> BuildingLayout:
    return FacilityService(repository(db)).get_layout()


@router.put("/layout", response_model=BuildingLayout)
def replace_layout(
    body: BuildingLayoutInput,
    db: Annotated[Session, Depends(get_db)],
    manager: Annotated[CurrentUser, Depends(require_manager)],
) -> BuildingLayout:
    del manager
    return FacilityService(repository(db)).replace_layout(body)
