import os
from datetime import datetime

from . import router, get_db
from database.models import User
from sqlalchemy.orm import Session
from fastapi import status, HTTPException, Depends, BackgroundTasks
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from pydantic import BaseModel
from typing import Optional


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


# Helpers
def send_message(message: Mail):
    sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
    sg.send(message)


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
    message.dynamic_template_data = {"year": year, "otp": otp}
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
        return "Thanks for contacting us!"
    except Exception:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="The email could not be sent"
        )
