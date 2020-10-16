import os
import hashlib
import secrets
import pytz
import boto3

from . import router, get_db
from fastapi import Depends, status, HTTPException
from database.models import User
from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
from passlib.hash import pbkdf2_sha256
from typing import Optional
from datetime import datetime
from .auth import create_access_token


# Schemas
class UserBase(BaseModel):
    id: Optional[int]
    name: str
    email: str
    mobile: Optional[str] = None
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
    subscription_status: bool

    class Config:
        schema_extra = {"example": {"subscription_status": False}}


class UserPasswordUpdate(BaseModel):
    password: str

    class Config:
        schema_extra = {"example": {"password": "supersecretpassword"}}


class UserEmailVerification(BaseModel):
    id: Optional[int]
    timestamp: Optional[datetime]

    class Config:
        schema_extra = {"example": {"id": 1}}


class UserOtpBase(BaseModel):
    id: int
    email: str

    class Config:
        orm_mode = True
        schema_extra = {"example": {"id": 1, "email": "JohnDoe@email.com"}}


# Helpers
def check_existing_user(db: Session, email: str) -> bool:
    email = email.lower()
    return db.query(User).filter(User.email == email).first()


def create_user_folders_in_s3(id: int):
    s3_resource = boto3.resource(
        "s3",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    folder_list = [f"users/{id}/profile/", f"users/{id}/ads/"]

    try:
        response = [
            s3_resource.Bucket(
                os.environ.get("AWS_STORAGE_BUCKET_NAME")
            ).put_object(Key=folder)
            for folder in folder_list
        ]

        if len(response) == 2:
            return True
    except Exception:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="Unable to connect to the storage service",
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

    return {"id": record.id, "email": record.email}


@router.get("/user/{user_id}", status_code=status.HTTP_200_OK)
def fetch_user(user_id: int, db: Session = Depends(get_db)):

    try:
        fetched_user = db.query(User).filter(User.id == user_id).first()

        return {
            "name": fetched_user.name,
            "email": fetched_user.email,
            "mobile": fetched_user.mobile,
            "apartment_id": fetched_user.apartment_id,
            "active_status": fetched_user.is_active,
        }
    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Unable to fetch user details"
        )


@router.post(
    "/register/user",
    response_model=UserCreate,
    status_code=status.HTTP_201_CREATED,
)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
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
        "mobile": new_user.mobile,
        "access_token": token,
        "email_verification_hash": email_verification_hash,
    }


@router.put("/user/update/{user_id}", status_code=status.HTTP_200_OK)
def update_user(user_id: int, user: UserUpdate, db: Session = Depends(get_db)):

    user_to_update = user.dict()

    try:
        db.query(User).filter(User.id == user_id).update(
            {
                User.name: user_to_update["name"].title(),
                User.email: user_to_update["email"].lower(),
                User.mobile: user_to_update["mobile"],
                User.apartment_id: user_to_update["apartment_id"],
            }
        )

        db.commit()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Unable to update user details"
        )

    return user_to_update


@router.put("/user/status/{user_id}", status_code=status.HTTP_200_OK)
def update_user_status(
    user_id: int, user: UserStatus, db: Session = Depends(get_db)
):
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


@router.put("/user/subscription/{user_id}", status_code=status.HTTP_200_OK)
def update_user_subscription_status(
    user_id: int, user: UserSubscriptionStatus, db: Session = Depends(get_db)
):
    try:
        db.query(User).filter(User.id == id).update(
            {User.mail_subscribed: user.dict()["subscription_status"]}
        )
        db.commit()
        return "User subscription deactivated"
    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Error updating user subscription status"
        )


@router.put("/user/password/{user_id}", status_code=status.HTTP_200_OK)
def update_user_password(
    user_id: int, user: UserPasswordUpdate, db: Session = Depends(get_db)
):
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
    user: UserEmailVerification, db: Session = Depends(get_db)
):
    try:
        db.query(User).filter(User.id == user.id).update(
            {User.email_verification_timestamp: datetime.utcnow()}
        )

        db.commit()

        return "Timestamp updated"
    except SQLAlchemyError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="The email timestamp could not be updated",
        )


@router.put("/user/otp_generation", status_code=status.HTTP_201_CREATED)
def generate_otp(user: UserOtpBase, db: Session = Depends(get_db)):
    email = user.email.lower()
    otp = secrets.token_hex(3).upper()

    try:
        db.query(User).filter(User.id == user.id, User.email == email).update(
            {User.otp: otp, User.otp_verification_timestamp: datetime.utcnow()}
        )

        db.commit()

        return "otp generated"
    except SQLAlchemyError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Error generating the otp"
        )


@router.get("/user/verify_otp/{user_id}", status_code=status.HTTP_200_OK)
def verify_otp(
    user_id: int, otp: str, timestamp: datetime, db: Session = Depends(get_db)
):
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
