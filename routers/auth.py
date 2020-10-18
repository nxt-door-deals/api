import os

from . import router, get_db
from datetime import datetime, timedelta
from collections import namedtuple

from fastapi import HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional
from passlib.hash import pbkdf2_sha256
from database.models import User, Apartment
from jose import jwt, JWTError


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
    credentials_exception = HTTPException(
        status_code=401,
        detail="Sorry! We could not validate those credentials",
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
            Apartment.name,
        )
        .filter(
            and_(
                User.id == int(token_data.id), User.apartment_id == Apartment.id
            )
        )
        .first()
    )

    if user is None:
        raise credentials_exception

    CurrentUser = namedtuple(
        "CurrentUser",
        "id name email is_active mobile mail_subscribed otp email_verified email_verification_hash email_verification_timestamp apartment_name",
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
        "apartment_name": user_dict["apartment_name"],
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