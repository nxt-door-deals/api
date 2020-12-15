import io
import locale
import os
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List
from typing import Optional

import boto3
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import status
from fastapi import UploadFile
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import get_db
from . import router
from database.models import Ad
from database.models import AdImage
from utils.helpers import get_posted_days


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
    images: List[UploadFile] = File(...)

    class Config:
        orm_mode = True


# Helpers
def upload_files_to_s3(
    ad_id: int, user_id: int, uploadedImages: List, db: Session
):
    s3_resource = boto3.resource(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    image_size = (800, 600)

    for image in uploadedImages:
        file_name, file_ext = os.path.splitext(image.filename)

        if file_ext == ".jpg":
            file_ext = ".jpeg"

        optimized_image = Image.open(image.file)
        optimized_image = optimized_image.resize(image_size)

        in_mem_file = io.BytesIO()
        optimized_image.save(in_mem_file, format=file_ext[1:], optimized=True)
        in_mem_file.seek(0)

        file_name = uuid.uuid4()

        # Add image to the bucket
        s3_resource.Bucket(os.getenv("AWS_STORAGE_BUCKET_NAME")).put_object(
            ACL="public-read",
            Body=in_mem_file,
            Key=f"users/{user_id}/ads/{ad_id}/{file_name}{file_ext}",
        )

        url_prefix = f"https://{os.getenv('AWS_STORAGE_BUCKET_NAME')}.s3.{os.getenv('AWS_DEFAULT_REGION')}.amazonaws.com"

        # Make an entry in the database
        new_ad = AdImage(
            ad_id=ad_id,
            image_path=f"{url_prefix}/users/{user_id}/ads/{ad_id}/{file_name}{file_ext}",
        )
        db.add(new_ad)
    try:
        db.commit()
    except Exception:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Could not make an image entry in the database",
        )


def get_images_from_s3(ad_id: int, db: Session):
    return db.query(AdImage.image_path).filter(AdImage.ad_id == ad_id).all()


def format_price(amount):
    locale.setlocale(locale.LC_ALL, "en_IN.UTF-8")

    # This is to avoid the trailing .00 for non-decimal numbers
    if Decimal(amount) % 1 != 0:
        return locale.currency(amount, symbol=False, grouping=True)

    return f"{amount:,}"


def get_ads(records: List, db: Session):
    ad_list = []
    ad_data = {}

    for record in records:
        formatted_price = format_price(record.price)

        ad_images = get_images_from_s3(record.id, db)

        ad_data["id"] = record.id
        ad_data["posted_by"] = record.posted_by
        ad_data["title"] = record.title
        ad_data["price"] = formatted_price
        ad_data["date_posted"] = get_posted_days(record.created_on)
        ad_data["images"] = [image["image_path"] for image in ad_images]
        ad_data["ad_type"] = record.ad_type

        ad_list.append(ad_data.copy())
    return ad_list


# End points
@router.post("/ads/create", status_code=status.HTTP_201_CREATED)
def create_ad(
    title: str = Form(...),
    ad_category: str = Form(...),
    description: str = Form(...),
    ad_type: str = Form(...),
    price: float = Form(...),
    negotiable: bool = Form(...),
    condition: str = Form(...),
    available_from: str = Form(...),
    publish_flat_number: bool = Form(...),
    posted_by: int = Form(...),
    apartment_id: int = Form(...),
    images: Optional[List[UploadFile]] = Form([]),
    db: Session = Depends(get_db),
):
    # Convert the string "available_from" to datetime
    available_from = datetime.strptime(available_from, "%Y-%m-%d %H:%M:%S")

    new_ad = Ad(
        title=title,
        description=description,
        ad_category=ad_category,
        ad_type=ad_type,
        price=price,
        negotiable=negotiable,
        condition=condition,
        available_from=available_from,
        publish_flat_number=publish_flat_number,
        posted_by=posted_by,
        apartment_id=apartment_id,
    )
    try:
        db.add(new_ad)
        db.commit()
        if images:
            upload_files_to_s3(new_ad.id, new_ad.posted_by, images, db)

    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Error creating a new advertisement"
        )
    return {
        "title": title,
        "description": description,
        "ad_category": ad_category,
        "ad_type": ad_type,
        "price": price,
        "negotiable": negotiable,
        "condition": condition,
        "available_from": available_from,
        "publish_flat_number": publish_flat_number,
        "posted_by": posted_by,
        "apartment_id": apartment_id,
    }


# Get ads for a particular neighbourhood
@router.get("/nbhads/get/{nbh_id}", status_code=status.HTTP_200_OK)
def get_ads_for_neighbourhood(nbh_id: int, db: Session = Depends(get_db)):
    records = (
        db.query(Ad)
        .filter(Ad.apartment_id == nbh_id)
        .order_by(Ad.created_on.desc())
        .all()
    )

    return get_ads(records, db)


# Search ads
@router.get("/search/ads", status_code=status.HTTP_200_OK)
def search_ads(
    nbh_id: int, category: str, search_text: str, db: Session = Depends(get_db)
):

    category = category or "%"
    search_text = "%" + search_text + "%" if search_text else "%"

    search_results = (
        db.query(Ad)
        .filter(
            and_(
                Ad.ad_category.ilike(category),
                Ad.apartment_id == nbh_id,
                or_(
                    Ad.title.ilike(search_text),
                    Ad.description.ilike(search_text),
                ),
            )
        )
        .order_by(Ad.created_on.desc())
        .all()
    )

    return get_ads(search_results, db)


# Search giveaways
@router.get("/search/ads/giveaway", status_code=status.HTTP_200_OK)
def search_giveaways(nbh_id: int, db: Session = Depends(get_db)):
    giveaway_list = (
        db.query(Ad)
        .filter(and_(Ad.apartment_id == nbh_id, Ad.ad_type == "giveaway"))
        .order_by(Ad.created_on.desc())
        .all()
    )

    return get_ads(giveaway_list, db)


# Sort by price - ascending
@router.get("/sort/ads/price_asc", status_code=status.HTTP_200_OK)
def sort_by_price_asc(nbh_id: int, db: Session = Depends(get_db)):
    price_asc_list = (
        db.query(Ad)
        .filter(and_(Ad.apartment_id == nbh_id, Ad.ad_type == "sale"))
        .order_by(Ad.price)
        .all()
    )

    return get_ads(price_asc_list, db)


# Sort by price - descending
@router.get("/sort/ads/price_desc", status_code=status.HTTP_200_OK)
def sort_by_price_desc(nbh_id: int, db: Session = Depends(get_db)):
    price_desc_list = (
        db.query(Ad)
        .filter(and_(Ad.apartment_id == nbh_id, Ad.ad_type == "sale"))
        .order_by(Ad.price.desc())
        .all()
    )

    return get_ads(price_desc_list, db)


# Sort by date posted - ascending
@router.get("/sort/ads/created_asc", status_code=status.HTTP_200_OK)
def sort_by_created_asc(nbh_id: int, db: Session = Depends(get_db)):
    created_asc_list = (
        db.query(Ad)
        .filter(Ad.apartment_id == nbh_id)
        .order_by(Ad.created_on)
        .all()
    )

    return get_ads(created_asc_list, db)


# Sort by date posted - descending
@router.get("/sort/ads/created_desc", status_code=status.HTTP_200_OK)
def sort_by_created_desc(nbh_id: int, db: Session = Depends(get_db)):
    created_desc_list = (
        db.query(Ad)
        .filter(Ad.apartment_id == nbh_id)
        .order_by(Ad.created_on.desc())
        .all()
    )

    return get_ads(created_desc_list, db)


# Giveaway - ascending
@router.get("/sort/ads/giveaway_asc", status_code=status.HTTP_200_OK)
def sort_by_giveaway_asc(nbh_id: int, db: Session = Depends(get_db)):
    giveaway_asc_list = (
        db.query(Ad)
        .filter(and_(Ad.apartment_id == nbh_id, Ad.ad_type == "giveaway"))
        .order_by(Ad.created_on)
        .all()
    )

    return get_ads(giveaway_asc_list, db)


# Giveaway - descending
@router.get("/sort/ads/giveaway_desc", status_code=status.HTTP_200_OK)
def sort_by_giveaway_desc(nbh_id: int, db: Session = Depends(get_db)):
    giveaway_desc_list = (
        db.query(Ad)
        .filter(and_(Ad.apartment_id == nbh_id, Ad.ad_type == "giveaway"))
        .order_by(Ad.created_on.desc())
        .all()
    )

    return get_ads(giveaway_desc_list, db)
