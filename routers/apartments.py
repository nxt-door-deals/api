from typing import List, Optional

from database.models import Apartment
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import get_db, router


# Schema
class ApartmentBase(BaseModel):
    id: Optional[int]
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
    try:
        return db.query(Apartment).all()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=500,
            detail="Error encountered while fetching apartments",
        )


# Endpoints
@router.get(
    "/apartments/all",
    response_model=List[ApartmentFetch],
    status_code=status.HTTP_200_OK,
)
def get_apartments(db: Session = Depends(get_db)):
    apartment = get_all_apartments(db)

    if not apartment:
        raise HTTPException(status_code=404, detail="Apartments not found")
    return apartment


@router.get(
    "/apartments/search/",
    response_model=List[ApartmentFetch],
    status_code=status.HTTP_200_OK,
)
def search_apartment(name: str, db: Session = Depends(get_db)):
    if name:
        name = "%" + name + "%"

    try:
        return (
            db.query(Apartment)
            .filter(and_(Apartment.name.ilike(name), Apartment.verified))
            .limit(4)
            .all()
        )
    except SQLAlchemyError:
        raise HTTPException(
            status_code=500,
            detail="Houston, we have a problem!\nCopy that, we are checking.",
        )


@router.post(
    "/apartments/add",
    response_model=ApartmentCreate,
    status_code=status.HTTP_201_CREATED,
)
def add_apartment(apartment: ApartmentCreate, db: Session = Depends(get_db)):

    # address2 is not mandatory. Hence format only if sent in the request
    address2 = apartment.address2.title() if apartment.address2 else None

    new_apartment = Apartment(
        name=apartment.name.title(),
        address1=apartment.address1.title(),
        address2=address2,
        city=apartment.city.title(),
        state=apartment.state.title(),
        pincode=apartment.pincode,
    )

    try:
        db.add(new_apartment)
        db.commit()
        return new_apartment
    except SQLAlchemyError:
        raise HTTPException(
            status_code=500,
            detail="Error encountered while adding new apartment",
        )
