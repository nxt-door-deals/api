import os
import re
from datetime import datetime

import boto3
import requests
from cryptography.fernet import Fernet
from jose import jwt
from sqlalchemy.orm import Session
from twilio.rest import Client

from database.models import User

# import requests

key = bytes(os.getenv("ENCRYPTION_KEY"), "utf-8")
fernet = Fernet(key)


def get_user_initial(name):
    split_name = name.split(" ")

    if len(split_name) == 1:
        return name[0].upper() + name[1].upper()

    if len(split_name) > 1:
        return split_name[0][0].upper() + split_name[1][0].upper()


# Remove excess spaces between words in a name
def name_checker(name):
    name_filter = [n for n in name.split(" ") if n != ""]

    return " ".join(name_filter)


def address_formatter(address):
    # We don't need numbers with st, nd, rd or th in title case
    address_regex_pattern = re.compile(
        r"([\d]+st)|([\d]+nd)|([\d]+rd)|([\d]+th)", re.IGNORECASE
    )

    matched_address = re.search(address_regex_pattern, address)

    if not matched_address:
        return address.title().strip()

    # Don't title case an address starting with 1st, 2nd, 3rd, 4th etc...
    # We don't want it to look like 1St, 2Nd, 3Rd, 4Th etc...
    formatted_address = [
        a.title().strip() if a != matched_address.group() else a.lower().strip()
        for a in address.split(" ")
    ]
    return " ".join(formatted_address)


def get_posted_days(posted_timestamp):
    current_date = datetime.now().date()
    # posted_date = datetime.strptime(posted_timestamp, "%Y-%m-%dT%H:%M%S.%f").date()

    posted_delta = current_date - posted_timestamp.date()

    # Get the number of days since the ad was posted
    posted_delta = int(posted_delta.total_seconds() / 3600 / 24)

    if posted_delta == 0:
        return "today"
    elif posted_delta == 1:
        return "yesterday"
    elif posted_delta >= 2 and posted_delta <= 30:
        return f"{posted_delta} days ago"
    elif posted_delta > 30:
        return "Over a month ago"


def initialize_s3():
    return boto3.resource(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def decode_token(token: str):
    if "Bearer" not in token:
        return False

    decoded_token = token.split(" ")

    decoded_token = jwt.decode(
        decoded_token[1], os.getenv("SECRET_KEY"), os.getenv("ALGORITHM")
    )

    return decoded_token


def generate_id_from_token(token: str, user_id: str):

    try:
        decoded_token = decode_token(token)
    except Exception:
        return False

    has_token_expired = datetime.utcnow() > datetime.fromtimestamp(
        decoded_token["exp"]
    )

    return decoded_token["sub"] == str(user_id) and not has_token_expired


def verify_id_from_token(token: str, db: Session):
    try:
        decoded_token = decode_token(token)
    except Exception:
        return False

    has_token_expired = datetime.utcnow() > datetime.fromtimestamp(
        decoded_token["exp"]
    )

    saved_id = db.query(User).filter(User.id == decoded_token["sub"]).first()

    if not saved_id:
        return False

    return saved_id and not has_token_expired


# def send_otp_sms(otp: str, mobile: str):
#     url = os.getenv("FAST2SMS_API_URL")

#     payload = f"variables_values={otp}&route=otp&numbers={mobile}"
#     headers = {
#         "authorization": os.getenv("FAST2SMS_API_KEY"),
#         "Content-Type": "application/x-www-form-urlencoded",
#         "Cache-Control": "no-cache",
#     }

# response = requests.request("POST", url, data=payload, headers=headers)


def send_sms_with_twilio(otp: str, mobile: str):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    client = Client(account_sid, auth_token)

    client.messages.create(
        body=f"Otp to reset your nxtdoordeals.com password - {otp}",
        from_=os.getenv("TWILIO_PHONE_NUMBER"),
        to=mobile,
    )


def send_ad_interest_sms_with_twilio(mobile: str, message: str):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    client = Client(account_sid, auth_token)

    client.messages.create(
        body=message,
        from_=os.getenv("TWILIO_PHONE_NUMBER"),
        to=mobile,
    )


def encrypt_mobile_number(mobile: str):
    encrypted_mobile = fernet.encrypt(mobile.encode())
    return encrypted_mobile.decode("utf-8")


def decrypt_mobile_number(encrypted_mobile: str):
    encrypted_mobile = bytes(encrypted_mobile, "utf-8")
    return fernet.decrypt(encrypted_mobile).decode()


def shorten_url(url: str):
    cuttly_api_key = os.getenv("CUTTLY_API_KEY")

    shortened_url = requests.get(
        f"https://cutt.ly/api/api.php?key={cuttly_api_key}&short={url}"
    ).json()["url"]

    if shortened_url["status"] == 7:
        return shortened_url["shortLink"]
    else:
        return False
