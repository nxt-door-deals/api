from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    String,
    Boolean,
    ForeignKey,
    BigInteger,
)
from sqlalchemy.orm import relationship

from database.db import Base


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
