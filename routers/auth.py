import os
from collections import namedtuple
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import Optional

from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from jose import JWTError
from passlib.hash import pbkdf2_sha256
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy import cast
from sqlalchemy import Date
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import get_db
from . import router
from database.models import Ad
from database.models import Apartment
from database.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth")


# Schemas
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    id: Optional[str]


class UserAuth(BaseModel):
    email: str
    password: str
    is_active: Optional[bool]


# Helpers


def get_password_hash(password: str):
    return pbkdf2_sha256.hash(password)


def verify_password(plain_password: str, password_hash: str):
    return pbkdf2_sha256.verify(plain_password, password_hash)


def authenticate_user(db: Session, email: str, password: str):
    email = email.lower()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=401, detail="Sorry! We cannot find that email address"
        )
    if not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=401, detail="Sorry! That password is incorrect"
        )
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    # sourcery skip: inline-immediately-returned-variable
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=1440)

    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(
        to_encode, os.getenv("SECRET_KEY"), algorithm=os.getenv("ALGORITHM")
    )
    return encoded_jwt


def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
):
    tdelta = timedelta(days=int(os.getenv("AD_EXPIRATION_TIME_DELTA")))
    credentials_exception = HTTPException(
        status_code=401,
        detail="Sorry! We could not validate those credentials",
        headers={"WWWW-Authenticate": "Bearer"},
    )

    if not token:
        return HTTPException(
            status_code=401,
            detail="Could not verify your credentials",
            headers={"WWWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token, os.getenv("SECRET_KEY"), os.getenv("ALGORITHM")
        )
        sub = payload.get("sub")

        if sub is None:
            raise credentials_exception
        token_data = TokenPayload(id=sub)
    except JWTError:
        raise credentials_exception

    user = (
        db.query(
            User.id,
            User.name,
            User.email,
            User.is_active,
            User.mobile,
            User.mail_subscribed,
            User.otp,
            User.email_verified,
            User.email_verification_hash,
            User.email_verification_timestamp,
            User.apartment_id,
            User.apartment_number,
            User.ads_path,
            User.profile_path,
            Apartment.name,
            func.count(Ad.id),
        )
        .filter(
            and_(
                User.id == int(token_data.id),
                User.apartment_id == Apartment.id,
                User.id == Ad.posted_by,
                Ad.active == True,  # noqa
                cast(Ad.created_on, Date) + tdelta > date.today(),
            )
        )
        .group_by(
            User.id,
            User.name,
            User.email,
            User.is_active,
            User.mobile,
            User.mail_subscribed,
            User.otp,
            User.email_verified,
            User.email_verification_hash,
            User.email_verification_timestamp,
            User.apartment_id,
            User.apartment_number,
            User.ads_path,
            User.profile_path,
            Apartment.name,
        )
        .first()
    )

    if user is None:
        raise credentials_exception

    CurrentUser = namedtuple(
        "CurrentUser",
        "id name email is_active mobile mail_subscribed otp email_verified email_verification_hash email_verification_timestamp apartment_id apartment_number ads_path profile_path apartment_name ad_count",
    )

    user_dict = CurrentUser._make(user)._asdict()

    return {
        "id": user_dict["id"],
        "name": user_dict["name"],
        "email": user_dict["email"],
        "is_active": user_dict["is_active"],
        "mobile": user_dict["mobile"],
        "mail_subscribed": user_dict["mail_subscribed"],
        "otp": user_dict["otp"],
        "email_verified": user_dict["email_verified"],
        "email_verification_hash": user_dict["email_verification_hash"],
        "email_verification_timestamp": user_dict[
            "email_verification_timestamp"
        ],
        "apartment_id": user_dict["apartment_id"],
        "apartment_number": user_dict["apartment_number"],
        "ads_path": user_dict["ads_path"],
        "profile_path": user_dict["profile_path"],
        "apartment_name": user_dict["apartment_name"],
        "ad_count": user_dict["ad_count"],
    }


def get_current_active_user(current_user: UserAuth = Depends(get_current_user)):
    if not current_user["is_active"]:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


# End points
@router.post("/auth", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    id = str(user.id)
    access_token_expires = timedelta(
        minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
    )
    access_token = create_access_token(
        data={"sub": id}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/auth/current_user", status_code=status.HTTP_200_OK)
def get_current_user(current_user: UserAuth = Depends(get_current_active_user)):
    return current_user
