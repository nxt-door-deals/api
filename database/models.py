from datetime import datetime

from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableList
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
    verification_hash = Column(String(100))
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
    ad_category = Column(String(50), nullable=False, index=True)
    ad_type = Column(String(50), nullable=False)
    price = Column(Numeric(scale=2))
    negotiable = Column(Boolean, default=False)
    condition = Column(String(50))
    available_from = Column(DateTime)
    publish_flat_number = Column(Boolean, default=False)
    active = Column(Boolean, default=True)
    sold = Column(Boolean, default=False)
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


class LikedAd(Base):
    __tablename__ = "likedads"

    id = Column(BigInteger, primary_key=True, nullable=False, index=True)
    ad_id = Column(Integer, ForeignKey("ads.id"))
    user_id = Column(Integer, ForeignKey("users.id"))

    ad = relationship("Ad")
    user = relationship("User")

    def __repr__(self):
        return f"LikedAd({self.ad_id}, {self.user_id})"


class Chat(Base):
    __tablename__ = "chats"

    id = Column(BigInteger, primary_key=True, nullable=False, index=True)
    ad_id = Column(Integer, ForeignKey("ads.id"))
    seller_id = Column(Integer)
    buyer_id = Column(Integer)
    chat_id = Column(String(64), unique=True, nullable=False)
    marked_del_seller = Column(Boolean, default=False)
    marked_del_buyer = Column(Boolean, default=False)
    blocked_by_seller = Column(Boolean, default=False)
    blocked_by_buyer = Column(Boolean, default=False)

    ad = relationship("Ad")

    def __repr__(self):
        return f"Chat({self.ad_id}, {self.seller_id}, {self.buyer_id})"


class ChatHistory(Base):
    __tablename__ = "chathistory"

    id = Column(BigInteger, primary_key=True, nullable=False, index=True)
    chat_id = Column(String(64), ForeignKey("chats.chat_id"), nullable=False)
    history = Column(MutableList.as_mutable(JSONB))
    new_notifications = Column(Boolean, default=False)

    chat = relationship("Chat")

    def __repr__(self):
        return f"ChatHistory({self.chat_id}, {self.history})"


class ReportedAd(Base):
    __tablename__ = "reportedads"

    id = Column(Integer, primary_key=True, index=True)
    ad_id = Column(Integer, ForeignKey("ads.id"), index=True)
    reported_by = Column(Integer, ForeignKey("users.id"), index=True)
    reason = Column(String(100), nullable=False)
    description = Column(String(5000), nullable=False)
    reported_on = Column(DateTime, default=datetime.now)

    ad = relationship("Ad")
    user = relationship("User")

    def __repr__(self):
        return f"ReportedAd({self.ad_id}, {self.reported_by}, {self.reason})"
