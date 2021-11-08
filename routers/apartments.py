import hashlib
import secrets
from typing import List
from typing import Optional

from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from pydantic import BaseModel
from sentry_sdk import capture_exception
from sqlalchemy import and_
from sqlalchemy.orm import Session

from . import get_db
from . import router
from database.models import Apartment
from routers.metrics import metric_counts
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
    except Exception as e:
        capture_exception(e)
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
            .limit(3)
            .all()
        )
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail="Houston, we have a problem!\nCopy that, we are checking.",
        )


@router.post("/apartments/add", status_code=status.HTTP_201_CREATED)
def add_apartment(apartment: ApartmentCreate, db: Session = Depends(get_db)):

    apartment_verification_hash = hashlib.sha256(
        secrets.token_hex(16).encode()
    ).hexdigest()

    address1_title = address_formatter(apartment.address1)

    if apartment.address2:
        address2_title = address_formatter(apartment.address2)

    new_apartment = Apartment(
        name=apartment.name.title().strip(),
        address1=address1_title.strip(),
        address2=address2_title if apartment.address2 else None,
        city=apartment.city.title().strip(),
        state=apartment.state.title(),
        pincode=apartment.pincode,
        submitted_by=apartment.submitted_by,
        verification_hash=apartment_verification_hash,
    )

    try:
        db.add(new_apartment)
        db.commit()

        metric_counts.increment_apartments_registered(db)

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

    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail="Error encountered while adding new apartment",
        )


@router.put("/verify/neighbourhood/", status_code=status.HTTP_200_OK)
def verify_neighbourhood(token: str, db: Session = Depends(get_db)):

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
    except Exception as e:
        capture_exception(e)
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
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching apartment",
        )
