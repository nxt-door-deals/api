import os
from datetime import date
from datetime import timedelta

from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy import cast
from sqlalchemy import Date
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import get_db
from . import router
from database.models import Ad
from database.models import Apartment


@router.get("/sitemap", status_code=status.HTTP_200_OK)
def generate_sitemap(db: Session = Depends(get_db)):
    try:
        routes = []
        faqs = ["seller", "buyer", "generic"]
        static_routes = [
            "/",
            "/account",
            "/login",
            "/guidelines",
            "/ourstory",
            "/policies",
            "/postad",
            "/registeruser",
        ]

        tdelta = timedelta(days=int(os.getenv("AD_EXPIRATION_TIME_DELTA")))

        [routes.append(route) for route in static_routes]

        ads = (
            db.query(Ad.id)
            .filter(
                Ad.active == True,  # noqa
                cast(Ad.created_on, Date) + tdelta > date.today(),
            )
            .all()
        )

        [routes.append(f"/ads/{ad[0]}") for ad in ads]

        apartments = (
            db.query(Apartment.id)
            .filter(Apartment.verified == True)  # noqa
            .all()
        )

        [
            routes.append(f"/neighbourhood/ads/{apartment[0]}")
            for apartment in apartments
        ]

        [routes.append(f"/faqs/{faq}") for faq in faqs]

        return routes
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not fetch urls",
        )
