from . import router, get_db
from fastapi import Depends, status, HTTPException
from database.models import User
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
from passlib.hash import pbkdf2_sha256
from typing import Optional


# Schemas
class UserBase(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    email: str
    mobile: Optional[int] = None
    apartment_id: int

    class Config:
        orm_mode = True


class UserCreate(UserBase):
    password: Optional[str] = None

    class Config:

        schema_extra = {
            "example": {
                "first_name": "John",
                "last_name": "Doe",
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
                "first_name": "John",
                "last_name": "Doe",
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
        schema_extra = {"eaxmple": {"password": "supersecretpassword"}}


# Helpers
def check_existing_user(db: Session, email: str) -> bool:
    user_email = db.query(User).filter(User.email == email).first()

    return True if user_email else False


# Endpoints
@router.get("/user/{user_id}", status_code=status.HTTP_200_OK)
def fetch_user(user_id: int, db: Session = Depends(get_db)):

    try:
        fetched_user = db.query(User).filter(User.id == user_id).first()

        return {
            "name": fetched_user.first_name + " " + fetched_user.last_name,
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

    # Format optional attributes
    last_name = user.last_name.title() if user.last_name else None

    # Check for duplicte email
    email = check_existing_user(db, user.email)

    if email:
        raise HTTPException(
            status_code=403,
            detail=f"An account for {user.email} already exists",
        )

    new_user = User(
        first_name=user.first_name.title(),
        last_name=last_name,
        email=user.email,
        mobile=user.mobile,
        hashed_password=hashed_password,
        apartment_id=user.apartment_id,
    )

    try:
        db.add(new_user)
        db.commit()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Error encountered while registering user"
        )

    return new_user


@router.put("/user/update/{user_id}", status_code=status.HTTP_200_OK)
def update_user(user_id: int, user: UserUpdate, db: Session = Depends(get_db)):

    user_to_update = user.dict()

    try:
        db.query(User).filter(User.id == user_id).update(
            {
                User.first_name: user_to_update["first_name"],
                User.last_name: user_to_update["last_name"],
                User.email: user_to_update["email"],
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
        return "User status updated" if True else "Error updating the status"
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
        return (
            "User subscription deactivated"
            if True
            else "Error updating the status"
        )
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

        return (
            "Password changed successfully"
            if True
            else "Error updating password"
        )
    except SQLAlchemyError:
        raise HTTPException(
            status_code=500, detail="Error updating the password"
        )
