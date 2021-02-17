import hashlib
import os
import secrets
from datetime import datetime
from typing import List
from typing import Optional

import pytz
from fastapi import BackgroundTasks
from fastapi import Depends
from fastapi import Header
from fastapi import HTTPException
from fastapi import status
from passlib.hash import pbkdf2_sha256
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import get_db
from . import router
from .auth import create_access_token
from database.models import Ad
from database.models import AdImage
from database.models import Chat
from database.models import ChatHistory
from database.models import LikedAd
from database.models import User
from utils.helpers import initialize_s3


# Schemas
class UserBase(BaseModel):
    id: Optional[int]
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
    id: Optional[int]
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
    except Exception:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Unable to connect to the storage service",
        )


def delete_s3_user_folder(user_id: int):
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

    except Exception:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="There was an error deleting the user folder",
        )


def delete_s3_ad_folders(user_id: int, ad_id: int):
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

    except Exception:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="There was an error deleting the ad folders",
        )


def get_user_ads(user_id: int, db: Session):
    return db.query(Ad.id).filter(Ad.posted_by == user_id).all()


def delete_user_ads(user_id: int, ads: List, db: Session):
    try:
        db.query(LikedAd).filter(LikedAd.user_id == user_id).delete(
            synchronize_session="fetch"
        )

        for ad in ads:
            db.query(AdImage).filter(AdImage.ad_id == ad[0]).delete(
                synchronize_session="fetch"
            )

        db.query(Ad).filter(Ad.posted_by == user_id).delete(
            synchronize_session="fetch"
        )

        db.commit()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete user ads",
        )


def delete_selected_ad(ad_id: int, db: Session):
    try:
        db.query(LikedAd).filter(LikedAd.ad_id == ad_id).delete(
            synchronize_session="fetch"
        )

        db.query(AdImage).filter(AdImage.ad_id == ad_id).delete(
            synchronize_session="fetch"
        )

        db.query(Ad).filter(Ad.id == ad_id).update({Ad.active: False})

        db.commit()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete user ads",
        )


def delete_user_records(user_id: int, ads: List, db: Session):
    try:
        delete_user_ads(user_id, ads, db)

        db.query(User).filter(User.id == user_id).delete(
            synchronize_session="fetch"
        )

        db.commit()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete user records",
        )


# Endpoints
@router.get("/user/validate_email/{email}", status_code=status.HTTP_200_OK)
def validate_email(email: str, db: Session = Depends(get_db)):
    record = check_existing_user(db, email)

    if not record:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Sorry, we could not find that email address",
        )

    return {"email": record.email}


@router.get("/user/{user_id}", status_code=status.HTTP_200_OK)
def fetch_user(
    user_id: int, db: Session = Depends(get_db), api_key: str = Header(None)
):

    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    try:
        fetched_user = db.query(User).filter(User.id == user_id).first()

        if fetched_user:
            return {
                "name": fetched_user.name,
                "email": fetched_user.email,
                "mobile": fetched_user.mobile,
                "apartment_id": fetched_user.apartment_id,
                "active_status": fetched_user.is_active,
            }
        else:
            return None

    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Unable to fetch user details"
        )


@router.post("/register/user", status_code=status.HTTP_201_CREATED)
def register_user(
    user: UserCreate, db: Session = Depends(get_db), api_key: str = Header(None)
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    # hash the password
    hashed_password = pbkdf2_sha256.hash(user.password)

    # Check for duplicte email
    email = check_existing_user(db, user.email)
    email_verification_hash = hashlib.sha256(
        secrets.token_hex(16).encode()
    ).hexdigest()

    if email:
        raise HTTPException(
            status_code=403,
            detail=f"An account for {user.email} already exists",
        )

    new_user = User(
        name=user.name.title(),
        email=user.email.lower(),
        mobile=user.mobile,
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
        token = create_access_token(
            data={
                "sub": id,
                "expires_delta": int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")),
            }
        )

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
    except SQLAlchemyError:
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
        "mobile": new_user.mobile,
        "access_token": token,
        "email_verification_hash": email_verification_hash,
    }


@router.delete("/user/delete/{user_id}", status_code=status.HTTP_202_ACCEPTED)
def delete_user(
    user_id: int,
    background_task: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    try:
        background_task.add_task(delete_s3_user_folder, user_id)

        ads = get_user_ads(user_id, db)

        background_task.add_task(delete_user_records, user_id, ads, db)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete user",
        )


@router.delete("/userads/delete/", status_code=status.HTTP_202_ACCEPTED)
def delete_user_ad(
    user_id: int,
    ad_id: int,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):

    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    try:
        delete_s3_ad_folders(user_id, ad_id)

        delete_selected_ad(ad_id, db)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete user ads",
        )


@router.put("/user/update/{user_id}", status_code=status.HTTP_200_OK)
def update_user(
    user_id: int,
    user: UserUpdate,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):

    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    user_to_update = user.dict()

    try:
        db.query(User).filter(User.id == user_id).update(
            {
                User.name: user_to_update["name"].title(),
                User.email: user_to_update["email"].lower(),
                User.mobile: user_to_update["mobile"],
                User.apartment_id: user_to_update["apartment_id"],
                User.apartment_number: user_to_update["apartment_number"],
            }
        )

        db.commit()
        return user_to_update
    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Unable to update user details"
        )


@router.put("/user/status/{user_id}", status_code=status.HTTP_200_OK)
def update_user_status(
    user_id: int,
    user: UserStatus,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    try:
        db.query(User).filter(User.id == user_id).update(
            {User.is_active: user.dict()["active_status"]}
        )
        db.commit()
        return "User status updated"
    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Error updating user activation status"
        )


@router.put("/user/subscription", status_code=status.HTTP_200_OK)
def update_user_subscription_status(
    user: UserSubscriptionStatus,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    try:
        db.query(User).filter(User.email == user.email).update(
            {
                User.mail_subscribed: user.dict()["subscription_status"],
                User.email: user.email,
            }
        )
        db.commit()
        return "User subscription status updated"
    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Error updating user subscription status"
        )


@router.put("/user/password/{user_id}", status_code=status.HTTP_200_OK)
def update_user_password(
    user_id: int,
    user: UserPasswordUpdate,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    new_password_hash = pbkdf2_sha256.hash(user.dict()["password"])

    try:
        db.query(User).filter(User.id == user_id).update(
            {User.hashed_password: new_password_hash}
        )
        db.commit()

        return "Password changed successfully"

    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating the password",
        )


@router.put("/user/emailverification/{token}", status_code=status.HTTP_200_OK)
def verify_user_email(
    token: str, user: UserEmailVerification, db: Session = Depends(get_db)
):

    message_tamper = 'Uh oh! There seems to be a problem with the verification link. Please try again with the link provided in our original email. Alternately, you can use the "Resend Email" option from your user account page'

    message_hours_elapsed = 'It has been over 24 hours since we sent the verification link. Please use the "Resend Email" option from your user account page to generate a new link'

    split_token = token.split("|")

    if len(split_token) != 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=message_tamper,
        )

    hash = split_token[0]
    user_id = int(split_token[1])

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
            return message_hours_elapsed

        db.query(User).filter(
            and_(User.id == user_id, User.email_verification_hash == hash)
        ).update({User.email_verified: True})

        db.commit()

        return "Thank you! Your email has been verified. You are now all set!"

    except SQLAlchemyError:
        raise HTTPException(
            status_code=500,
            detail="Error updating the email verification status",
        )


@router.put("/email_timestamp/refresh", status_code=status.HTTP_200_OK)
def email_timestamp_refresh(
    user: UserEmailVerification,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    try:
        db.query(User).filter(User.id == user.id).update(
            {User.email_verification_timestamp: datetime.utcnow()}
        )

        db.commit()

        return "Email timestamp updated"
    except SQLAlchemyError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="The email timestamp could not be updated",
        )


@router.put("/user/otp_generation", status_code=status.HTTP_201_CREATED)
def generate_otp(
    user: UserOtpBase,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):

    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    email = user.email.lower()
    otp = secrets.token_hex(3).upper()

    try:
        db.query(User).filter(User.email == email).update(
            {User.otp: otp, User.otp_verification_timestamp: datetime.utcnow()}
        )

        db.commit()

        record = db.query(User).filter(User.email == email).first()

        return {
            "id": record.id,
            "email": record.email,
            "otp_verification_timestamp": record.otp_verification_timestamp,
        }
    except SQLAlchemyError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Error generating the otp"
        )


@router.get("/user/verify_otp/{user_id}", status_code=status.HTTP_200_OK)
def verify_otp(
    user_id: int,
    otp: str,
    timestamp: datetime,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    try:
        record = (
            db.query(User.otp, User.otp_verification_timestamp)
            .filter(User.id == user_id)
            .first()
        )
        saved_otp_verification_timestamp = record.otp_verification_timestamp.replace(
            tzinfo=pytz.UTC
        )

        date_diff = timestamp - saved_otp_verification_timestamp

        if int(date_diff.total_seconds()) > 600:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="The otp has expired. Please initiate the password reset process again.",
            )

        if record.otp == otp.upper():
            return "Otp verified successfully"
        else:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="The otp is incorrect."
            )
    except SQLAlchemyError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="The otp entered is either incorrect or has expired",
        )


@router.put("/otp_timestamp/refresh", status_code=status.HTTP_200_OK)
def otp_timestamp_refresh(
    user: UserOtpVerification,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

    try:
        db.query(User).filter(User.id == user.id).update(
            {User.otp_verification_timestamp: datetime.utcnow()}
        )

        db.commit()

        return "Otp timestamp updated"
    except SQLAlchemyError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="The otp timestamp could not be updated",
        )


@router.get("/chats/seller/{user_id}", status_code=status.HTTP_200_OK)
def get_chats_as_seller(
    user_id: int, db: Session = Depends(get_db), api_key: str = Header(None)
):

    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

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
                    Ad.active == True,  # noqa
                    Chat.marked_del_seller == False,  # noqa
                )
            )
            .all()
        )

    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No seller chat record found",
        )


@router.get("/chats/buyer/{user_id}", status_code=status.HTTP_200_OK)
def get_chats_as_buyer(
    user_id: int, db: Session = Depends(get_db), api_key: str = Header(None)
):

    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )

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
                    Ad.active == True,  # noqa
                    Chat.marked_del_buyer == False,  # noqa
                )
            )
            .all()
        )

    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No buyer chat record found",
        )


@router.put("/seller/chat/delete/", status_code=status.HTTP_201_CREATED)
def mark_seller_chat_for_deletion(
    seller_id: int,
    chat_id: str,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )
    try:
        db.query(Chat).filter(
            Chat.seller_id == seller_id, Chat.chat_id == chat_id
        ).update({Chat.marked_del_seller: True})

        db.commit()

        return "Chat marked for deletion"
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not mark record for deletion",
        )


@router.put("/buyer/chat/delete/", status_code=status.HTTP_201_CREATED)
def mark_buyer_chat_for_deletion(
    buyer_id: int,
    chat_id: str,
    db: Session = Depends(get_db),
    api_key: str = Header(None),
):
    if api_key != os.getenv("PROJECT_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uh uh uh! You didn't say the magic word...",
        )
    try:
        db.query(Chat).filter(
            Chat.buyer_id == buyer_id, Chat.chat_id == chat_id
        ).update({Chat.marked_del_buyer: True})

        db.commit()

        return "Chat marked for deletion"
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not mark record for deletion",
        )
