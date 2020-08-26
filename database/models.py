from datetime import datetime

from sqlalchemy import Column, Integer, DateTime, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import TSVECTOR

from database.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(50), unique=True, nullable=False)
    mobile = Column(Integer)
    password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    apartment_id = Column(Integer, ForeignKey("apartments.id"))
    created_on = Column(DateTime, default=datetime.now)
    last_updated = Column(DateTime, onupdate=datetime.now)
    apartment = relationship("Apartment", back_populates="user")

    def __repr__(self):
        return f"User({self.first_name} + ' ' + {self.last_name}, {self.email}, {self.is_active})"


class Apartment(Base):
    __tablename__ = "apartments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    address1 = Column(String(150), nullable=False)
    address2 = Column(String(150))
    city = Column(String(50), nullable=False)
    state = Column(String(50), nullable=False)
    pincode = Column(Integer, nullable=False)
    name_token = Column(TSVECTOR)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_on = Column(DateTime, default=datetime.now)
    last_updated = Column(DateTime, onupdate=datetime.now)
    user = relationship("User", back_populates="apartment")

    def __repr__(self):
        return (
            f"Apartment({self.name}, {self.city}, {self.state}, {self.pincode})"
        )
