import hashlib
import os
import secrets
from typing import List
from typing import Optional

from fastapi import Depends
from fastapi import Header
from fastapi import HTTPException
from fastapi import status
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import get_db
from . import router
from database.models import Apartment
from utils.helpers import address_formatter


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
    submitted_by: str

    class Config:
        schema_extra = {
            "example": {
                "name": "Republic of Whitefield",
                "address1": "EPIP Zone",
                "address2": "Whitefield",
                "city": "Bengaluru",
                "state": "Karnataka",
                "pincode": "560066",
                "submitted_by": "customer@randomemail.com",
            }
        }


# Helpers
def get_all_apartments(db: Session):
    try:
        return db.query(Apartment).all()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Apartments not found"
        )
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


@router.post("/apartments/add", status_code=status.HTTP_201_CREATED)
def add_apartment(
    apartment: ApartmentCreate,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):

    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    apartment_verification_hash = hashlib.sha256(
        secrets.token_hex(16).encode()
    ).hexdigest()

    address1_title = address_formatter(apartment.address1)

    if apartment.address2:
        address2_title = address_formatter(apartment.address2)

    new_apartment = Apartment(
        name=apartment.name.title().strip(),
        address1=address1_title.strip(),
        address2=address2_title,
        city=apartment.city.title().strip(),
        state=apartment.state.title(),
        pincode=apartment.pincode,
        submitted_by=apartment.submitted_by,
        verification_hash=apartment_verification_hash,
    )

    try:
        db.add(new_apartment)
        db.commit()

        return {
            "id": new_apartment.id,
            "name": new_apartment.name,
            "address1": new_apartment.address1,
            "address2": new_apartment.address2,
            "city": new_apartment.city,
            "state": new_apartment.state,
            "pincode": new_apartment.pincode,
            "submitted_by": new_apartment.submitted_by,
            "verification_hash": new_apartment.verification_hash,
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=500,
            detail="Error encountered while adding new apartment",
        )


@router.put("/verify/neighbourhood/", status_code=status.HTTP_200_OK)
def verify_neighbourhood(
    token: str, db: Session = Depends(get_db), api_key: str = Header(None)
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    split_token = token.split("|")

    verification_hash = split_token[0]
    neighbourhood_id = split_token[1]

    try:
        record = (
            db.query(Apartment)
            .filter(
                and_(
                    Apartment.id == neighbourhood_id,
                    Apartment.verification_hash == verification_hash,
                )
            )
            .first()
        )

        if not record:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Could not find the apartment"
            )

        db.query(Apartment).filter(
            and_(
                Apartment.id == neighbourhood_id,
                Apartment.verification_hash == verification_hash,
            )
        ).update({Apartment.verified: True})

        db.commit()

        return {"name": record.name, "email": record.submitted_by}
    except SQLAlchemyError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not verify neighbourhood",
        )


@router.get("/apartments/{id}", status_code=status.HTTP_200_OK)
def get_apartment_from_id(id: int, db: Session = Depends(get_db)):

    try:
        record = (
            db.query(Apartment)
            .filter(Apartment.id == id, Apartment.verified == True)  # noqa
            .first()
        )

        if not record:
            return None

        return {"name": record.name}
    except SQLAlchemyError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching apartment",
        )
