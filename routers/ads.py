import io
import os
import uuid
from datetime import date
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from math import trunc
from typing import List
from typing import Optional

from babel.numbers import format_decimal
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import Header
from fastapi import HTTPException
from fastapi import status
from fastapi import UploadFile
from PIL import ExifTags
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy import cast
from sqlalchemy import Date
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import get_db
from . import router
from database.models import Ad
from database.models import AdImage
from database.models import Apartment
from database.models import Chat
from database.models import ReportedAd
from database.models import User
from utils.helpers import generate_id_from_token
from utils.helpers import get_posted_days
from utils.helpers import initialize_s3


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


class ReportAd(BaseModel):
    ad_id: int
    reported_by: int
    reason: str
    description: str

    class Config:
        orm_mode = True


# Helpers

# This function is mainly for images clicked on phones where the exif data causes image rotation
def fix_image_orientation(optimized_image):
    for orientation in ExifTags.TAGS.keys():
        if ExifTags.TAGS[orientation] == "Orientation":
            break

    exif = optimized_image._getexif()

    if exif:
        if 274 in exif.keys():
            if exif[274] == 3:
                optimized_image = optimized_image.rotate(180, expand=True)
            elif exif[274] == 6:
                optimized_image = optimized_image.rotate(270, expand=True)
            elif exif[274] == 8:
                optimized_image = optimized_image.rotate(90, expand=True)
    else:
        return optimized_image

    return optimized_image


def upload_files_to_s3(
    ad_id: int, user_id: int, uploadedImages: List, db: Session
):
    s3_resource = initialize_s3()

    image_size = (800, 600)

    for image in uploadedImages:
        file_name, file_ext = os.path.splitext(image.filename)

        if file_ext == ".jpg":
            file_ext = ".jpeg"

        optimized_image = Image.open(image.file)

        optimized_image = fix_image_orientation(optimized_image)

        if (
            optimized_image.width < image_size[0]
            or optimized_image.height < image_size[1]
        ):
            image_size = (optimized_image.width, optimized_image.height)

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

        return True
    except Exception:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Could not make an image entry in the database",
        )


def get_images_from_s3(ad_id: int, db: Session):
    return db.query(AdImage.image_path).filter(AdImage.ad_id == ad_id).all()


def format_price(amount):

    # This is to avoid the trailing .00 for non-decimal numbers
    if Decimal(amount) % 1 != 0:
        return format_decimal(amount, locale="en_IN")

    return format_decimal(trunc(amount), locale="en_IN")


def check_for_chat_record(ad_id: int, user_id: int, db: Session):

    chat_record = (
        db.query(Chat)
        .filter(and_(Chat.ad_id == ad_id, Chat.seller_id == user_id))
        .all()
    )

    if not chat_record:
        return 0

    return len(chat_record)


def get_ads(records: List, db: Session):
    ad_list = []
    ad_data = {}

    today = datetime.today().date()
    tdelta = timedelta(days=int(os.getenv("AD_EXPIRATION_TIME_DELTA")))

    for record in records:

        # Check if ad was reported more than 5 times
        ad_reported_record = reported_ad_check(record.id, db)

        if not ad_reported_record:
            chat_record = check_for_chat_record(record.id, record.posted_by, db)
            formatted_price = format_price(record.price)

            ad_images = get_images_from_s3(record.id, db)

            ad_data["id"] = record.id
            ad_data["posted_by"] = record.posted_by
            ad_data["title"] = record.title
            ad_data["price"] = formatted_price
            ad_data["date_posted"] = get_posted_days(record.created_on)
            ad_data["images"] = [image["image_path"] for image in ad_images]
            ad_data["ad_type"] = record.ad_type
            ad_data["ad_category"] = record.ad_category
            ad_data["condition"] = record.condition
            ad_data["chat_record_count"] = chat_record

            # Don't add the ad to the list if it is older than 30 days
            if record.created_on.date() + tdelta > today:
                ad_list.append(ad_data.copy())
    return ad_list


# Delete individual images from the edit ad page
def delete_individual_image(user_id: int, ad_id: int, image: str):
    s3_resource = initialize_s3()

    bucket = s3_resource.Bucket(os.getenv("AWS_STORAGE_BUCKET_NAME"))

    try:
        object_to_delete = [
            {"Key": object.key}
            for object in bucket.objects.filter(
                Prefix=f"users/{user_id}/ads/{ad_id}/{image}"
            )
        ]

        if object_to_delete:
            bucket.delete_objects(Delete={"Objects": object_to_delete})

        return "Image deleted"
    except Exception:
        return "Image not deleted"


def reported_ad_check(ad_id: int, db: Session = Depends(get_db)):
    return (
        db.query(ReportedAd.ad_id)
        .filter(ReportedAd.ad_id == ad_id)
        .group_by(ReportedAd.ad_id)
        .having(func.count(ReportedAd.ad_id) >= 5)
        .all()
    )


def list_all_ads(db: Session = Depends(get_db)):
    tdelta = timedelta(days=int(os.getenv("AD_EXPIRATION_TIME_DELTA")))
    try:
        return (
            db.query(Ad)
            .filter(
                Ad.active == True,  # noqa
                cast(Ad.created_on, Date) + tdelta > date.today(),
            )
            .all()
        )
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not fetch all ads",
        )


def increment_user_ad_count(user_id: int, db: Session = Depends(get_db)):
    try:
        # Get current ad count for the user
        current_ad_count = (
            db.query(User.ads_to_date).filter(User.id == user_id).first()
        )

        # Increment the count
        db.query(User).filter(User.id == user_id).update(
            {User.ads_to_date: current_ad_count[0] + 1}
        )

        db.commit()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not increment ad count",
        )


# End points
@router.get("/ads/all", status_code=status.HTTP_200_OK)
def get_all_ads(db: Session = Depends(get_db)):
    ads = list_all_ads(db)

    if not ads:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ads not found"
        )
    return ads


# Fetch ad from ad id - returning None will redirect to 404.js
@router.get("/ads/{id}", status_code=status.HTTP_200_OK)
def get_ad_details_from_id(id: int, db: Session = Depends(get_db)):

    ad = {}

    today = datetime.today().date()
    tdelta = timedelta(days=int(os.getenv("AD_EXPIRATION_TIME_DELTA")))

    try:
        ad_record = (
            db.query(Ad).filter(Ad.id == id, Ad.active == True).first()  # noqa
        )

        if not ad_record:
            return None

        # Check if ad is older than 30 days
        if not ad_record.created_on.date() + tdelta > today:
            return None

        neighbourhood = (
            db.query(Apartment.name)
            .filter(Apartment.id == ad_record.apartment_id)
            .first()
        )

        # Check if ad was reported more than 5 times
        ad_reported_record = reported_ad_check(id, db)

        # 404 if the ad has been reported 5 or more times
        if ad_reported_record:
            return None

        user_record = (
            db.query(User).filter(User.id == ad_record.posted_by).first()
        )

        price = format_price(ad_record.price)
        ad_images = get_images_from_s3(ad_record.id, db)

        available_from = (
            "immediately"
            if ad_record.available_from < datetime.today()
            else ad_record.available_from
        )

        modified_id = ad_record.ad_category[0] + "AD" + str(ad_record.id)

        ad["id"] = ad_record.id
        ad["modified_id"] = modified_id
        ad["title"] = ad_record.title
        ad["description"] = ad_record.description
        ad["category"] = ad_record.ad_category
        ad["ad_type"] = ad_record.ad_type
        ad["price"] = price
        ad["negotiable"] = ad_record.negotiable
        ad["condition"] = ad_record.condition
        ad["available_from"] = available_from
        ad["available_from_date"] = ad_record.available_from
        ad["sold"] = ad_record.sold
        ad["images"] = [image["image_path"] for image in ad_images]
        ad["apartment_id"] = ad_record.apartment_id
        ad["apartment_name"] = neighbourhood.name
        ad["flat_no"] = (
            user_record.apartment_number
            if ad_record.publish_flat_number
            else None
        )
        ad["active"] = ad_record.active
        ad["posted_by_name"] = user_record.name
        ad["posted_by_id"] = user_record.id
        ad["posted_by_email"] = user_record.email

        return ad
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not fetch ad details",
        )


# Create an ad
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

        increment_user_ad_count(posted_by, db)

        if images:
            upload_files_to_s3(new_ad.id, new_ad.posted_by, images, db)
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

    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Error creating a new advertisement"
        )


# Update an ad
@router.put("/ads/update", status_code=status.HTTP_201_CREATED)
def update_ad(
    ad_id: int,
    posted_by_id: int,
    title: str = Form(...),
    description: str = Form(...),
    ad_type: str = Form(...),
    price: float = Form(...),
    negotiable: bool = Form(...),
    condition: str = Form(...),
    available_from: str = Form(...),
    publish_flat_number: bool = Form(...),
    images: Optional[List[UploadFile]] = Form([]),
    db: Session = Depends(get_db),
):
    # Convert the string "available_from" to datetime
    available_from = datetime.strptime(available_from, "%Y-%m-%d %H:%M:%S")
    try:
        db.query(Ad).filter(Ad.id == ad_id).update(
            {
                Ad.title: title,
                Ad.description: description,
                Ad.ad_type: ad_type,
                Ad.price: price,
                Ad.negotiable: negotiable,
                Ad.condition: condition,
                Ad.available_from: available_from,
                Ad.publish_flat_number: publish_flat_number,
            }
        )
        db.commit()

        if images:
            upload_files_to_s3(ad_id, posted_by_id, images, db)

        return "Ad updated"

    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Error updating advertisement"
        )


# Mark item as sold
@router.put("/ad/sold/{ad_id}", status_code=status.HTTP_201_CREATED)
def mark_ad_as_sold(
    ad_id: int, db: Session = Depends(get_db), api_key: str = Header(None)
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    try:
        db.query(Ad).filter(Ad.id == ad_id).update({Ad.sold: True})
        db.commit()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could nt mark item as sold",
        )


# Get ads for a particular neighbourhood
@router.get("/nbhads/get/{nbh_id}", status_code=status.HTTP_200_OK)
def get_ads_for_neighbourhood(nbh_id: int, db: Session = Depends(get_db)):
    records = (
        db.query(Ad)
        .filter(and_(Ad.apartment_id == nbh_id, Ad.active == True))  # noqa
        .order_by(Ad.created_on.desc())
        .all()
    )

    return get_ads(records, db)


# Get ads for a particular user
@router.get("/userads/get/{user_id}", status_code=status.HTTP_200_OK)
def get_ads_for_user(user_id: int, db: Session = Depends(get_db)):
    records = (
        db.query(Ad)
        .filter(and_(Ad.posted_by == user_id, Ad.active == True))  # noqa
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
                Ad.active == True,  # noqa
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
        .filter(
            and_(
                Ad.apartment_id == nbh_id,
                Ad.ad_type == "giveaway",
                Ad.active == True,  # noqa
            )
        )
        .order_by(Ad.created_on.desc())
        .all()
    )

    return get_ads(giveaway_list, db)


# Sort by price - ascending
@router.get("/sort/ads/price_asc", status_code=status.HTTP_200_OK)
def sort_by_price_asc(nbh_id: int, db: Session = Depends(get_db)):
    price_asc_list = (
        db.query(Ad)
        .filter(
            and_(
                Ad.apartment_id == nbh_id,
                Ad.ad_type == "sale",
                Ad.active == True,  # noqa
            )
        )
        .order_by(Ad.price)
        .all()
    )

    return get_ads(price_asc_list, db)


# Sort by price - descending
@router.get("/sort/ads/price_desc", status_code=status.HTTP_200_OK)
def sort_by_price_desc(nbh_id: int, db: Session = Depends(get_db)):
    price_desc_list = (
        db.query(Ad)
        .filter(
            and_(
                Ad.apartment_id == nbh_id,
                Ad.ad_type == "sale",
                Ad.active == True,  # noqa
            )
        )
        .order_by(Ad.price.desc())
        .all()
    )

    return get_ads(price_desc_list, db)


# Sort by date posted - ascending
@router.get("/sort/ads/created_asc", status_code=status.HTTP_200_OK)
def sort_by_created_asc(nbh_id: int, db: Session = Depends(get_db)):
    created_asc_list = (
        db.query(Ad)
        .filter(Ad.apartment_id == nbh_id, Ad.active == True)  # noqa
        .order_by(Ad.created_on)
        .all()
    )

    return get_ads(created_asc_list, db)


# Sort by date posted - descending
@router.get("/sort/ads/created_desc", status_code=status.HTTP_200_OK)
def sort_by_created_desc(nbh_id: int, db: Session = Depends(get_db)):
    created_desc_list = (
        db.query(Ad)
        .filter(Ad.apartment_id == nbh_id, Ad.active == True)  # noqa
        .order_by(Ad.created_on.desc())
        .all()
    )

    return get_ads(created_desc_list, db)


# Giveaway - ascending
@router.get("/sort/ads/giveaway_asc", status_code=status.HTTP_200_OK)
def sort_by_giveaway_asc(nbh_id: int, db: Session = Depends(get_db)):
    giveaway_asc_list = (
        db.query(Ad)
        .filter(
            and_(
                Ad.apartment_id == nbh_id,
                Ad.ad_type == "giveaway",
                Ad.active == True,  # noqa
            )
        )
        .order_by(Ad.created_on)
        .all()
    )

    return get_ads(giveaway_asc_list, db)


# Giveaway - descending
@router.get("/sort/ads/giveaway_desc", status_code=status.HTTP_200_OK)
def sort_by_giveaway_desc(nbh_id: int, db: Session = Depends(get_db)):
    giveaway_desc_list = (
        db.query(Ad)
        .filter(
            and_(
                Ad.apartment_id == nbh_id,
                Ad.ad_type == "giveaway",
                Ad.active == True,  # noqa
            )
        )
        .order_by(Ad.created_on.desc())
        .all()
    )

    return get_ads(giveaway_desc_list, db)


@router.delete("/image/delete", status_code=status.HTTP_202_ACCEPTED)
def delete_image(
    user_id: int,
    ad_id: int,
    image: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    if "Bearer" not in authorization:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    if generate_id_from_token(authorization, user_id):

        try:
            delete_individual_image(user_id, ad_id, image)

            db.query(AdImage).filter(
                AdImage.image_path.ilike("%" + image + "%")
            ).delete(synchronize_session="fetch")

            db.commit()
            return "Image deleted"
        except SQLAlchemyError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Image could not be deleted",
            )
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@router.get("/reported/{ad_id}", status_code=status.HTTP_200_OK)
def get_reported_ads(
    ad_id: int, db: Session = Depends(get_db), api_key: str = Header(None)
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    try:
        reported_ad_records = (
            db.query(ReportedAd).filter(ReportedAd.ad_id == ad_id).all()
        )

        return {
            "users": [
                reported_ad.reported_by for reported_ad in reported_ad_records
            ]
        }
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No records found"
        )


@router.post("/report/ad", status_code=status.HTTP_201_CREATED)
def report_ad(
    ad: ReportAd,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    if "Bearer" not in authorization:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    if generate_id_from_token(authorization, ad.reported_by):

        new_report = ReportedAd(
            ad_id=ad.ad_id,
            reported_by=ad.reported_by,
            reason=ad.reason,
            description=ad.description,
        )

        try:
            db.add(new_report)
            db.commit()

            return {"msg": f"Ad {ad.ad_id} reported"}

        except SQLAlchemyError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not report ad",
            )
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
