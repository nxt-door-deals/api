# import os
from datetime import datetime
from typing import Optional

# from database.models import Ad
from fastapi import Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import get_db, router


# Schemas
class AdsBase(BaseModel):
    id: Optional[int]
    title: str
    description: str
    ad_category: str
    ad_type: str
    price: float
    negotiable: Optional[bool] = False
    condition: str
    available_from: Optional[datetime] = datetime.today().date()
    publish_flat_number: Optional[bool] = False
    posted_by: int
    apartment_id: int

    class Config:
        orm_mode = True


# End points
@router.post(
    "/ads/create", response_class=AdsBase, status_code=status.HTTP_201_CREATED
)
def create_ad(ad: AdsBase, db: Session = Depends(get_db)):
    pass
    # new_ad = Ad(
    #     title=ad.title,
    #     description=ad.description,
    #     ad_category=ad.ad_category,
    #     ad_type=ad.ad_type,
    #     price=ad.price,
    #     negotiable=ad.negotiable,
    #     condition=ad.condition,
    #     available_from=ad.available_from,
    #     publish_flat_number=ad.publish_flat_number,
    #     posted_by=ad.posted_by,
    #     apartment_id=ad.apartment_id,
    # )
