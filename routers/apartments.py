from fastapi import HTTPException, Depends, status
from database.models import Apartment
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from . import router, get_db


# Schema
class ApartmentBase(BaseModel):
    name: str
    address1: str
    address2: Optional[str] = None
    city: str
    state: str
    pincode: str

    class Config:
        orm_mode = True


class ApartmentFetch(ApartmentBase):
    verified: bool


class ApartmentCreate(ApartmentBase):
    pass

    class Config:
        schema_extra = {
            "example": {
                "name": "Republic of Whitefield",
                "address1": "EPIP Zone",
                "address2": "Whitefield",
                "city": "Bengaluru",
                "state": "Karnataka",
                "pincode": "560066",
            }
        }


# Helpers
def get_all_apartments(db: Session):
    return db.query(Apartment).all()


# Endpoints
@router.get(
    "/apartments/all",
    response_model=List[ApartmentFetch],
    status_code=status.HTTP_200_OK,
)
async def get_apartments(db: Session = Depends(get_db)):
    apartment = get_all_apartments(db)

    if not apartment:
        raise HTTPException(status_code=404, detail="Apartments not found")
    return apartment


@router.get(
    "/apartments/search/",
    response_model=List[ApartmentFetch],
    status_code=status.HTTP_200_OK,
)
async def search_apartment(name: str, db: Session = Depends(get_db)):
    apartment = (
        db.query(Apartment).filter(Apartment.name.ilike("%" + name + "%")).all()
    )

    if not apartment:
        raise HTTPException(
            status_code=404, detail="No apartment matches that search criteria"
        )
    return apartment


@router.post(
    "/apartments/add",
    response_model=ApartmentCreate,
    status_code=status.HTTP_201_CREATED,
)
async def add_apartment(
    apartment: ApartmentCreate, db: Session = Depends(get_db)
):
    new_apartment = Apartment(
        name=apartment.name.title(),
        address1=apartment.address1.title(),
        address2=apartment.address2.title(),
        city=apartment.city.title(),
        state=apartment.state.title(),
        pincode=apartment.pincode,
    )
    db.add(new_apartment)
    db.commit()
    return new_apartment
