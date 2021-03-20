import os
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from pydantic import BaseModel
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from sqlalchemy.orm import Session

from . import get_db
from . import router
from database.models import User
from utils.helpers import address_formatter


class EmailSend(BaseModel):
    from_email: str
    to_email: str
    template_name: Optional[str]
    subject: Optional[str]
    body: Optional[str]
    name: Optional[str]
    verificationurl: Optional[str]
    year: Optional[str]

    class Config:
        orm_mode = True

        schema_extra = {
            "example": {
                "from_email": "sender@email.com",
                "to_email": "sendee@email.com",
            }
        }


class NbhEmailSend(EmailSend):
    apartment_name: str
    address1: str
    address2: str
    city: str
    state: str
    pincode: str
    verificationurl: str
    email: str

    class Config:
        schema_extra = {
            "example": {
                "from_email": "sender@email.com",
                "to_email": "sendee@email.com",
            }
        }


class NbhEmailSendUser(EmailSend):
    apartment_name: str
    email: str

    class Config:
        schema_extra = {
            "example": {
                "from_email": "sender@email.com",
                "to_email": "sendee@email.com",
            }
        }


class ReportedAdEmail(EmailSend):
    description: Optional[str]
    ad_title: str
    ad_id: Optional[int]

    class Config:
        schema_extra = {
            "example": {
                "from_email": "sender@email.com",
                "to_email": "sendee@email.com",
                "description": "some description",
                "ad_id": 1,
            }
        }


# Helpers
def send_message(message: Mail):
    sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
    sg.send(message)


# Endpoints
@router.post("/email/send", status_code=status.HTTP_202_ACCEPTED)
def send_email(email: EmailSend, background_task: BackgroundTasks):
    message = Mail(from_email=email.from_email, to_emails=email.to_email)

    name = email.name or None
    verification_url = email.verificationurl or None
    year = email.year or datetime.now().year

    # Dynamic data in the templates
    message.dynamic_template_data = {
        "name": name,
        "verificationurl": verification_url,
        "year": year,
    }

    message.template_id = os.getenv(email.template_name)

    try:
        background_task.add_task(send_message, message)
        return status.HTTP_202_ACCEPTED
    except Exception:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="The email could not be sent"
        )


@router.post("/email/send/otp", status_code=status.HTTP_202_ACCEPTED)
def send_email_otp(
    email: EmailSend,
    background_task: BackgroundTasks,
    db: Session = Depends(get_db),
):
    message = Mail(from_email=email.from_email, to_emails=email.to_email)

    year = email.year or datetime.now().year
    try:
        otp = db.query(User.otp).filter(User.email == email.to_email).first()
    except Exception:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="There was a problem generating the otp",
        )

    # Dynamic data in the templates
    message.dynamic_template_data = {"year": year, "otp": otp[0]}
    message.template_id = os.getenv(email.template_name)

    try:
        background_task.add_task(send_message, message)
        return status.HTTP_202_ACCEPTED
    except Exception:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="The email could not be sent"
        )


@router.post("/email/send/contact", status_code=status.HTTP_202_ACCEPTED)
def send_email_contact(email: EmailSend, background_task: BackgroundTasks):
    # from_email has to be the authenticated sender in Sendgrid
    message = Mail(
        from_email=email.from_email,
        to_emails=email.to_email,
        subject="You have a new message",
        plain_text_content=email.body,
    )
    try:
        background_task.add_task(send_message, message)
        return "We'll be in touch soon!"
    except Exception:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="The email could not be sent"
        )


# Method to send an email to contact@nxtdoordeals.com during registration
@router.post(
    "/email/send/nbhregistration", status_code=status.HTTP_202_ACCEPTED
)
def send_nbh_registration_email(
    email: NbhEmailSend, background_task: BackgroundTasks
):
    message = Mail(from_email=email.from_email, to_emails=email.to_email)

    email.address1 = address_formatter(email.address1)

    if email.address2:
        email.address2 = address_formatter(email.address2)

    message.dynamic_template_data = {
        "apartment_name": email.apartment_name.title()
        if email.apartment_name
        else None,
        "address1": email.address1 or None,
        "address2": email.address2 or None,
        "city": email.city.title() if email.city else None,
        "state": email.state.title() if email.state else None,
        "pincode": email.pincode or None,
        "email": email.email.lower() if email.email else None,
        "verificationurl": email.verificationurl,
        "year": email.year or datetime.now().year,
    }

    message.template_id = os.getenv(email.template_name)

    try:
        background_task.add_task(send_message, message)
        return status.HTTP_202_ACCEPTED
    except Exception:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="The email could not be sent"
        )


# Method to send an email to the user after registration
@router.post(
    "/email/send/nbhregistration_user", status_code=status.HTTP_202_ACCEPTED
)
def send_nbh_registration_email_to_user(
    email: NbhEmailSendUser, background_task: BackgroundTasks
):
    message = Mail(from_email=email.from_email, to_emails=email.to_email)

    message.dynamic_template_data = {
        "apartment_name": email.apartment_name.title()
        if email.apartment_name
        else None,
        "email": email.email.lower() if email.email else None,
        "year": email.year or datetime.now().year,
    }

    message.template_id = os.getenv(email.template_name)

    try:
        background_task.add_task(send_message, message)
        return status.HTTP_202_ACCEPTED
    except Exception:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="The email could not be sent"
        )


# Send email to seller and us when an ad is reported or removed
@router.post("/email/reported_ad/", status_code=status.HTTP_202_ACCEPTED)
def send_reported_ad_email_to_user(
    email: ReportedAdEmail, background_task: BackgroundTasks
):

    if email.template_name == "REPORTED_AD_NOTIFY_OWNERS_TEMPLATE":
        email.to_email = email.from_email

    message = Mail(from_email=email.from_email, to_emails=email.to_email)

    message.dynamic_template_data = {
        "description": email.description,
        "ad_title": email.ad_title,
        "ad_id": email.ad_id,
        "year": email.year or datetime.now().year,
    }

    message.template_id = os.getenv(email.template_name)

    try:
        background_task.add_task(send_message, message)
        return status.HTTP_202_ACCEPTED
    except Exception:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="The email could not be sent"
        )
