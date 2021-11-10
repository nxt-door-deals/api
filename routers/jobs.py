import datetime
import os
from typing import List
from typing import Optional

from fastapi import Depends
from fastapi import Header
from fastapi import HTTPException
from fastapi import status
from pydantic import BaseModel
from sentry_sdk import capture_exception
from sqlalchemy import cast
from sqlalchemy import Date
from sqlalchemy.orm import Session

from . import get_db
from . import router
from database.models import Ad
from database.models import Job
from routers.user import delete_s3_ad_folders
from routers.user import delete_selected_ad


class AdDeletion(BaseModel):
    ad_list: Optional[List]


def verify_job_id(job_secret: str):
    return os.getenv("JOB_SECRET_KEY") == job_secret


@router.get("/expired_ads", status_code=status.HTTP_200_OK)
async def get_expired_ads(
    db: Session = Depends(get_db),
    secret: str = Header(None),
):
    tdelta = datetime.timedelta(days=int(os.getenv("AD_EXPIRATION_TIME_DELTA")))

    expired_ad_list = []
    expired_ad = {}

    if not (verify_job_id(secret)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized"
        )

    try:
        expired_ads = (
            db.query(Ad)
            .filter(
                cast(Ad.created_on, Date) + tdelta < datetime.date.today(),
                Ad.active == True,  # noqa
            )
            .all()
        )

        for ad in expired_ads:
            expired_ad["ad_id"] = ad.id
            expired_ad["posted_by"] = ad.posted_by

            expired_ad_list.append(expired_ad.copy())

        return expired_ad_list
    except Exception as e:
        capture_exception(e)


@router.delete("/delete_ads", status_code=status.HTTP_200_OK)
async def delete_expired_ads(
    ads: AdDeletion, db: Session = Depends(get_db), secret: str = Header(None)
):
    if not (verify_job_id(secret)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized"
        )

    try:
        for ad in ads.ad_list:
            delete_s3_ad_folders(ad["posted_by"], ad["ad_id"])
            delete_selected_ad(ad["ad_id"], db)

        return "All expired ads deleted"
    except Exception as e:
        capture_exception(e)


@router.put("/jobs", status_code=status.HTTP_201_CREATED)
async def update_job_run_date(
    job_id: str, db: Session = Depends(get_db), secret: str = Header(None)
):

    if not (verify_job_id(secret)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized"
        )

    try:
        db.query(Job).filter(Job.job_id == job_id).update(
            {Job.last_run_date: datetime.date.today()}
        )

        db.commit()
    except Exception as e:
        capture_exception(e)
