import hashlib
import os
import secrets
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import List
from typing import Optional
from uuid import UUID

import pytz
from fastapi import BackgroundTasks
from fastapi import Depends
from fastapi import Header
from fastapi import HTTPException
from fastapi import status
from passlib.hash import pbkdf2_sha256
from pydantic import BaseModel
from sentry_sdk import capture_exception
from sqlalchemy import and_
from sqlalchemy import cast
from sqlalchemy import Date
from sqlalchemy.orm import Session

from . import get_db
from . import router
from .auth import create_access_token
from database.models import Ad
from database.models import AdImage
from database.models import Chat
from database.models import ChatHistory
from database.models import LikedAd
from database.models import ReportedAd
from database.models import User
from routers.metrics import metric_counts
from utils.helpers import decrypt_mobile_number
from utils.helpers import encrypt_mobile_number
from utils.helpers import generate_id_from_token
from utils.helpers import initialize_s3
from utils.helpers import send_sms_with_twilio

# from utils.helpers import send_otp_sms


# Schemas
class UserBase(BaseModel):
    id: Optional[str]
    name: str
    email: str
    mobile: Optional[str] = None
    apartment_number: str
    apartment_id: int

    class Config:
        orm_mode = True


class UserCreate(UserBase):
    password: str
    access_token: Optional[str]
    email_verification_hash: Optional[str]

    class Config:
        schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "JD@gmail.com",
                "mobile": "9845099899",
                "apartment_id": 1,
                "password": "password",
            }
        }


class UserUpdate(UserBase):
    pass

    class Config:
        schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "JD@gmail.com",
                "mobile": "9845099899",
                "apartment_id": 1,
            }
        }


class UserStatus(BaseModel):
    active_status: bool

    class Config:
        schema_extra = {"example": {"active_status": False}}


class UserSubscriptionStatus(BaseModel):
    email: str
    subscription_status: bool

    class Config:
        schema_extra = {
            "example": {
                "email": "email@example.com",
                "subscription_status": False,
            }
        }


class UserPasswordUpdate(BaseModel):
    password: str

    class Config:
        schema_extra = {"example": {"password": "supersecretpassword"}}


class UserEmailVerification(BaseModel):
    id: Optional[str]
    timestamp: Optional[datetime]

    class Config:
        schema_extra = {"example": {"id": 1}}


class UserOtpVerification(UserEmailVerification):
    pass


class UserOtpBase(BaseModel):
    email: str

    class Config:
        orm_mode = True
        schema_extra = {"example": {"id": 1, "email": "JohnDoe@email.com"}}


# Helpers
def check_existing_user(db: Session, email: str) -> bool:
    email = email.lower()
    return db.query(User).filter(User.email == email).first()


def create_user_folders_in_s3(id: int):
    s3_resource = initialize_s3()

    folder_list = [f"users/{id}/profile/", f"users/{id}/ads/"]

    try:
        response = [
            s3_resource.Bucket(os.getenv("AWS_STORAGE_BUCKET_NAME")).put_object(
                Key=folder
            )
            for folder in folder_list
        ]

        if len(response) == 2:
            return True
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Unable to connect to the storage service",
        )


def delete_s3_user_folder(user_id: str):
    s3_resource = initialize_s3()

    bucket = s3_resource.Bucket(os.getenv("AWS_STORAGE_BUCKET_NAME"))

    try:
        objects_to_delete = [
            {"Key": object.key}
            for object in bucket.objects.filter(Prefix=f"users/{user_id}")
        ]

        if objects_to_delete:
            bucket.delete_objects(Delete={"Objects": objects_to_delete})
            return "Folders deleted"
        else:
            return "No folders to delete"

    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="There was an error deleting the user folder",
        )


def delete_s3_ad_folders(user_id: str, ad_id: UUID):
    s3_resource = initialize_s3()

    bucket = s3_resource.Bucket(os.getenv("AWS_STORAGE_BUCKET_NAME"))

    try:
        objects_to_delete = [
            {"Key": object.key}
            for object in bucket.objects.filter(
                Prefix=f"users/{user_id}/ads/{ad_id}"
            )
        ]

        if objects_to_delete:
            bucket.delete_objects(Delete={"Objects": objects_to_delete})
            return "Ad folders deleted"
        else:
            return "No ad folders to delete"

    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="There was an error deleting the ad folders",
        )


def get_user_ads(user_id: str, db: Session):
    return db.query(Ad.id).filter(Ad.posted_by == user_id).all()


def delete_user_ads(user_id: str, ads: List, db: Session):
    try:
        db.query(LikedAd).filter(LikedAd.user_id == user_id).delete(
            synchronize_session="fetch"
        )

        for ad in ads:
            db.query(AdImage).filter(AdImage.ad_id == str(ad[0])).delete(
                synchronize_session="fetch"
            )

        db.query(Ad).filter(Ad.posted_by == user_id).delete(
            synchronize_session="fetch"
        )

        db.query(ReportedAd).filter(ReportedAd.reported_by == user_id).delete(
            synchronize_session="fetch"
        )

        db.commit()
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete user ads",
        )


def delete_selected_ad(ad_id: UUID, db: Session):
    try:
        db.query(LikedAd).filter(LikedAd.ad_id == str(ad_id)).delete(
            synchronize_session="fetch"
        )

        db.query(AdImage).filter(AdImage.ad_id == str(ad_id)).delete(
            synchronize_session="fetch"
        )

        db.query(Ad).filter(Ad.id == str(ad_id)).update({Ad.active: False})

        db.commit()
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete user ads",
        )


def delete_user_records(user_id: str, ads: List, db: Session):
    try:
        delete_user_ads(user_id, ads, db)

        db.query(User).filter(User.id == user_id).delete(
            synchronize_session="fetch"
        )

        db.commit()
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete user records",
        )


def increment_generated_otp_count(
    email: str, otp_generated_count: int, db: Session
):
    db.query(User).filter(User.email == email).update(
        {User.otp_generated_count: otp_generated_count + 1}
    )

    db.commit()


def lock_otp_delivery(email: str, db: Session):
    db.query(User).filter(User.email == email).update(
        {User.otp_locked_timestamp: datetime.utcnow(), User.lock_otp_send: True}
    )

    db.commit()


def reset_otp_count(email: str, db):
    db.query(User).filter(User.email == email).update(
        {
            User.otp_generated_count: 0,
            User.lock_otp_send: False,
            User.otp_locked_timestamp: None,
            User.invalid_otp_count: 0,
        }
    )

    db.commit()


def increment_invalid_otp_count(user_id: int, otp_count: int, db: Session):
    db.query(User).filter(User.id == user_id).update(
        {User.invalid_otp_count: otp_count + 1}
    )

    db.commit()


# Endpoints
@router.get("/user/validate_email/{email}", status_code=status.HTTP_200_OK)
def validate_email(email: str, db: Session = Depends(get_db)):
    record = check_existing_user(db, email)

    if not record:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Sorry, we could not find that email address",
        )

    db.query(User).filter(User.email == email).update(
        {User.invalid_otp_count: 0}
    )

    db.commit()

    return {"email": record.email}


@router.get("/user/{user_id}", status_code=status.HTTP_200_OK)
def fetch_user(
    user_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    try:
        fetched_user = db.query(User).filter(User.id == user_id).first()

        if fetched_user:
            return {
                "name": fetched_user.name,
                "email": fetched_user.email,
                # "mobile": fetched_user.mobile,
                "apartment_id": fetched_user.apartment_id,
                "active_status": fetched_user.is_active,
            }
        else:
            return None

    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=500, detail="Unable to fetch user details"
        )


@router.post("/register/user", status_code=status.HTTP_201_CREATED)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    # hash the password
    hashed_password = pbkdf2_sha256.hash(user.password)

    # Check for duplicate email
    email = check_existing_user(db, user.email)
    email_verification_hash = hashlib.sha256(
        secrets.token_hex(16).encode()
    ).hexdigest()

    if email:
        raise HTTPException(
            status_code=403,
            detail=f"An account for {user.email.lower()} already exists",
        )

    encrypted_mobile = (
        encrypt_mobile_number(f"+91{user.mobile}") if user.mobile else None
    )

    new_user = User(
        name=user.name.title(),
        email=user.email.lower(),
        mobile=encrypted_mobile,
        hashed_password=hashed_password,
        apartment_id=user.apartment_id,
        apartment_number=user.apartment_number,
        email_verification_hash=email_verification_hash,
        email_verification_timestamp=datetime.utcnow(),
    )

    try:
        db.add(new_user)
        db.commit()

        id = str(new_user.id)
        token = create_access_token(data={"sub": id})

        create_user_folders_in_s3(new_user.id)

        # Once the folders are created in s3, update the paths in the table
        bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")
        region = os.getenv("AWS_DEFAULT_REGION")
        base_aws_s3_path = f"https://{bucket}.s3.{region}.amazonaws.com/users/"

        db.query(User).filter(User.id == new_user.id).update(
            {
                User.profile_path: os.path.join(
                    base_aws_s3_path, f"{new_user.id}/profile/"
                ),
                User.ads_path: os.path.join(
                    base_aws_s3_path, f"{new_user.id}/ads/"
                ),
            }
        )

        db.commit()

        metric_counts.increment_registered_users(db)

    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=500, detail="Error encountered while registering user"
        )

    return {
        "id": new_user.id,
        "name": new_user.name,
        "email": new_user.email,
        "password": new_user.hashed_password,
        "apartment_id": new_user.apartment_id,
        "apartment_number": new_user.apartment_number,
        "access_token": token,
        "email_verification_hash": email_verification_hash,
    }


@router.delete("/user/delete/{user_id}", status_code=status.HTTP_202_ACCEPTED)
def delete_user(
    user_id: str,
    background_task: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    if not generate_id_from_token(authorization, user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session Expired"
        )

    try:
        metric_counts.increment_deleted_user_accounts(db)
        background_task.add_task(delete_s3_user_folder, user_id)

        ads = get_user_ads(user_id, db)
        background_task.add_task(delete_user_records, user_id, ads, db)

    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete user",
        )


@router.delete("/userads/delete/", status_code=status.HTTP_202_ACCEPTED)
def delete_user_ad(
    user_id: str,
    ad_id: UUID,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    if not generate_id_from_token(authorization, user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session Expired"
        )

    try:
        delete_s3_ad_folders(user_id, ad_id)

        delete_selected_ad(ad_id, db)
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete user ads",
        )


@router.put("/user/update/{user_id}", status_code=status.HTTP_200_OK)
def update_user(
    user_id: str,
    user: UserUpdate,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):

    if not generate_id_from_token(authorization, user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session Expired"
        )

    user_to_update = user.dict()

    encrypted_mobile = (
        encrypt_mobile_number(f"+91{user_to_update['mobile']}")
        if user_to_update["mobile"]
        else None
    )

    try:
        db.query(User).filter(User.id == user_id).update(
            {
                User.name: user_to_update["name"].title(),
                User.email: user_to_update["email"].lower(),
                User.mobile: encrypted_mobile,
                User.apartment_id: user_to_update["apartment_id"],
                User.apartment_number: user_to_update["apartment_number"],
            }
        )

        db.commit()
        return user_to_update
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=500, detail="Unable to update user details"
        )


@router.put("/user/status/{user_id}", status_code=status.HTTP_200_OK)
def update_user_status(
    user_id: str,
    user: UserStatus,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):

    if not generate_id_from_token(authorization, user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session Expired"
        )

    try:
        db.query(User).filter(User.id == user_id).update(
            {User.is_active: user.dict()["active_status"]}
        )
        db.commit()
        return "User status updated"
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=500, detail="Error updating user activation status"
        )


@router.put("/user/subscription", status_code=status.HTTP_200_OK)
def update_user_subscription_status(
    user: UserSubscriptionStatus, db: Session = Depends(get_db)
):
    try:
        db.query(User).filter(User.email == user.email).update(
            {
                User.mail_subscribed: user.dict()["subscription_status"],
                User.email: user.email,
            }
        )
        db.commit()
        return "User subscription status updated"
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=500, detail="Error updating user subscription status"
        )


@router.put("/user/password/{user_id}", status_code=status.HTTP_200_OK)
def update_user_password(
    user_id: str, user: UserPasswordUpdate, db: Session = Depends(get_db)
):
    new_password_hash = pbkdf2_sha256.hash(user.dict()["password"])

    try:
        db.query(User).filter(User.id == user_id).update(
            {User.hashed_password: new_password_hash}
        )
        db.commit()

        return "Password changed successfully"

    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating the password",
        )


@router.put("/user/emailverification/{token}", status_code=status.HTTP_200_OK)
def verify_user_email(
    token: str, user: UserEmailVerification, db: Session = Depends(get_db)
):

    message_tamper = 'Uh oh! There seems to be a problem with the verification link. Please try again with the link provided in our original email. Alternately, you can use the <span class="text-purple-500 font-semibold">Resend Email</span> option from your user account page.'

    message_hours_elapsed = 'It has been over 24 hours since we sent the verification link. Please use the <span class="text-purple-500 font-semibold">Resend Email</span> option from your user account page to generate a new link.'

    split_token = token.split("|")

    if len(split_token) != 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=message_tamper,
        )

    hash = split_token[0]
    user_id = split_token[1]

    try:
        record = (
            db.query(User)
            .filter(
                and_(User.id == user_id, User.email_verification_hash == hash)
            )
            .first()
        )

        if not record:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=message_tamper,
            )

        if record.email_verified:
            return "This email has already been verified. No further action required."

        date_diff = (
            user.timestamp
            - record.email_verification_timestamp.replace(tzinfo=pytz.UTC)
        )
        if int(date_diff.total_seconds() / 3600) > 24:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=message_hours_elapsed,
            )

        db.query(User).filter(
            and_(User.id == user_id, User.email_verification_hash == hash)
        ).update({User.email_verified: True})

        db.commit()

        return "Thank you! Your email has been verified. You are now all set!"

    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=500,
            detail="Error updating the email verification status",
        )


@router.put("/email_timestamp/refresh", status_code=status.HTTP_200_OK)
def email_timestamp_refresh(
    user: UserEmailVerification,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    if not generate_id_from_token(authorization, user.id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session Expired"
        )

    try:
        db.query(User).filter(User.id == user.id).update(
            {User.email_verification_timestamp: datetime.utcnow()}
        )

        db.commit()

        return "Email timestamp updated"
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="The email timestamp could not be updated",
        )


@router.put("/user/otp_generation", status_code=status.HTTP_201_CREATED)
def generate_otp(user: UserOtpBase, db: Session = Depends(get_db)):
    email = user.email.lower()
    otp = secrets.token_hex(3).upper()

    record = check_existing_user(db, email)

    if record.invalid_otp_count >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many invalid otp's. Please enter your email again",
        )

    if (
        record.lock_otp_send
        and datetime.utcnow()
        > record.otp_locked_timestamp + timedelta(minutes=10)
    ):
        reset_otp_count(email, db)

    if record.otp_generated_count >= 3:
        lock_otp_delivery(email, db)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many otp requests. Please wait for 10 minutes before regenerating an otp",
        )

    try:

        db.query(User).filter(User.email == email).update(
            {User.otp: otp, User.otp_verification_timestamp: datetime.utcnow()}
        )

        db.commit()

        record = db.query(User).filter(User.email == email).first()

        if record.mobile:
            # send_otp_sms(otp, record.mobile)
            decrypted_mobile = decrypt_mobile_number(record.mobile)
            send_sms_with_twilio(otp, decrypted_mobile)

        increment_generated_otp_count(email, record.otp_generated_count, db)

        return {
            "id": record.id,
            "email": record.email,
            "otp_verification_timestamp": record.otp_verification_timestamp,
            "count": record.otp_generated_count,
        }
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Error generating the otp"
        )


@router.get("/user/verify_otp/{user_id}", status_code=status.HTTP_200_OK)
def verify_otp(
    user_id: str, otp: str, timestamp: datetime, db: Session = Depends(get_db)
):
    record = (
        db.query(
            User.otp,
            User.otp_verification_timestamp,
            User.email,
            User.invalid_otp_count,
        )
        .filter(User.id == user_id)
        .first()
    )

    if record.invalid_otp_count >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many invalid otp's. Please enter your email again",
        )

    saved_otp_verification_timestamp = (
        record.otp_verification_timestamp.replace(tzinfo=pytz.UTC)
    )

    date_diff = timestamp - saved_otp_verification_timestamp

    if int(date_diff.total_seconds()) > 600:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="The otp has expired. Please initiate the password reset process again.",
        )

    if record.otp == otp.upper():
        reset_otp_count(record.email, db)
        return "Otp verified successfully"
    else:
        increment_invalid_otp_count(user_id, record.invalid_otp_count, db)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="The otp is incorrect"
        )


@router.put("/otp_timestamp/refresh", status_code=status.HTTP_200_OK)
def otp_timestamp_refresh(
    user: UserOtpVerification, db: Session = Depends(get_db)
):
    try:
        db.query(User).filter(User.id == user.id).update(
            {User.otp_verification_timestamp: datetime.utcnow()}
        )

        db.commit()

        return "Otp timestamp updated"
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="The otp timestamp could not be updated",
        )


@router.get("/chats/seller/{user_id}", status_code=status.HTTP_200_OK)
def get_chats_as_seller(
    user_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    if not generate_id_from_token(authorization, user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session Expired"
        )

    tdelta = timedelta(days=int(os.getenv("AD_EXPIRATION_TIME_DELTA")))
    try:
        return (
            db.query(
                User.name.label("buyer_name"),
                Ad.title.label("ad_title"),
                Chat.chat_id.label("chat_id"),
                Chat.ad_id.label("ad_id"),
                Chat.buyer_id.label("buyer_id"),
                Chat.seller_id.label("seller_id"),
                ChatHistory.new_notifications.label("new_chats"),
                ChatHistory.history[-1]["sender"].label("last_sender"),
                Chat.marked_del_seller.label("marked_for_deletion"),
            )
            .filter(
                and_(
                    User.id == Chat.buyer_id,
                    Ad.id == Chat.ad_id,
                    Chat.chat_id == ChatHistory.chat_id,
                    Chat.seller_id == user_id,
                    cast(Ad.created_on, Date) + tdelta > date.today(),
                    Ad.active == True,  # noqa
                    Chat.marked_del_seller == False,  # noqa
                )
            )
            .all()
        )

    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No seller chat record found",
        )


@router.get("/chats/buyer/{user_id}", status_code=status.HTTP_200_OK)
def get_chats_as_buyer(
    user_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    if not generate_id_from_token(authorization, user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session Expired"
        )

    tdelta = timedelta(days=int(os.getenv("AD_EXPIRATION_TIME_DELTA")))

    try:
        return (
            db.query(
                User.name.label("seller_name"),
                Ad.title.label("ad_title"),
                Chat.chat_id.label("chat_id"),
                Chat.ad_id.label("ad_id"),
                Chat.buyer_id.label("buyer_id"),
                Chat.seller_id.label("seller_id"),
                ChatHistory.new_notifications.label("new_chats"),
                ChatHistory.history[-1]["sender"].label("last_sender"),
                Chat.marked_del_buyer.label("marked_for_deletion"),
            )
            .filter(
                and_(
                    User.id == Chat.seller_id,
                    Ad.id == Chat.ad_id,
                    Chat.chat_id == ChatHistory.chat_id,
                    Chat.buyer_id == user_id,
                    cast(Ad.created_on, Date) + tdelta > date.today(),
                    Ad.active == True,  # noqa
                    Chat.marked_del_buyer == False,  # noqa
                )
            )
            .all()
        )

    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No buyer chat record found",
        )


@router.put("/seller/chat/delete/", status_code=status.HTTP_201_CREATED)
def mark_seller_chat_for_deletion(
    seller_id: str,
    chat_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    if not generate_id_from_token(authorization, seller_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session Expired"
        )

    try:
        db.query(Chat).filter(
            Chat.seller_id == seller_id, Chat.chat_id == chat_id
        ).update({Chat.marked_del_seller: True})

        db.commit()

        return "Chat marked for deletion"
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not mark record for deletion",
        )


@router.put("/buyer/chat/delete/", status_code=status.HTTP_201_CREATED)
def mark_buyer_chat_for_deletion(
    buyer_id: str,
    chat_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    if not generate_id_from_token(authorization, buyer_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session Expired"
        )

    try:
        db.query(Chat).filter(
            Chat.buyer_id == buyer_id, Chat.chat_id == chat_id
        ).update({Chat.marked_del_buyer: True})

        db.commit()

        return "Chat marked for deletion"
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not mark record for deletion",
        )


# Update the number sold for the user
@router.put("/update/sold/{user_id}", status_code=status.HTTP_201_CREATED)
def update_number_sold(
    user_id: str,
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    if not generate_id_from_token(authorization, user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session Expired"
        )

    try:
        existing_number_sold = (
            db.query(User.number_sold).filter(User.id == user_id).first()
        )

        new_number_sold = existing_number_sold[0] + 1

        db.query(User).filter(User.id == user_id).update(
            {User.number_sold: new_number_sold}
        )
        db.commit()

        metric_counts.increment_items_sold(db)
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update the number sold",
        )
