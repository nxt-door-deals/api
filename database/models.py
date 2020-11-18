from datetime import datetime

from database.db import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(50), unique=True, nullable=False, index=True)
    mobile = Column(String(15))
    hashed_password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    apartment_id = Column(Integer, ForeignKey("apartments.id"))
    apartment_number = Column(String(10), nullable=False, default="1234")
    mail_subscribed = Column(Boolean, default=True)
    created_on = Column(DateTime, default=datetime.now)
    otp = Column(String(6))
    otp_verification_timestamp = Column(DateTime)
    email_verified = Column(Boolean, default=False)
    email_verification_hash = Column(String(100))
    email_verification_timestamp = Column(DateTime)
    profile_path = Column(String(500))
    ads_path = Column(String(500))

    apartment = relationship("Apartment")

    def __repr__(self):
        return f"User({self.id}, {self.name}, {self.email}, {self.is_active})"


class Apartment(Base):
    __tablename__ = "apartments"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True)
    address1 = Column(String(150), nullable=False)
    address2 = Column(String(150))
    city = Column(String(50), nullable=False)
    state = Column(String(50), nullable=False)
    pincode = Column(String(15), nullable=False)
    verified = Column(Boolean, default=False)
    submitted_by = Column(String(50))
    created_on = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return (
            f"Apartment({self.name}, {self.city}, {self.state}, {self.pincode})"
        )


class Ad(Base):
    __tablename__ = "ads"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    title = Column(String(100), nullable=False)
    description = Column(String(10000), nullable=False)
    ad_category = Column(String(20), nullable=False, index=True)
    ad_type = Column(String(15), nullable=False)
    price = Column(Numeric(precision=2))
    negotiable = Column(Boolean, default=False)
    condition = Column(String(20))
    available_from = Column(DateTime)
    publish_flat_number = Column(Boolean, default=False)
    posted_by = Column(Integer, ForeignKey("users.id"))
    apartment_id = Column(Integer, ForeignKey("apartments.id"))
    created_on = Column(DateTime, default=datetime.now)

    user = relationship("User")
    apartment = relationship("Apartment")

    def __repr__(self):
        return f"Ad({self.id}, {self.title})"


class AdImage(Base):
    __tablename__ = "adimages"

    id = Column(BigInteger, primary_key=True, nullable=False, index=True)
    ad_id = Column(Integer, ForeignKey("ads.id"))
    image_path = Column(String(500), nullable=False)

    image = relationship("Ad")

    def __repr__(self):
        return f"AdImages({self.ad_id}, {self.image_path})"
