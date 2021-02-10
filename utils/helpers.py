import os
import re
from datetime import datetime

import boto3


def address_formatter(address):
    # We don't need numbers with st, nd, rd or th in title case
    address_regex_pattern = re.compile(
        r"([\d]+st)|([\d]+nd)|([\d]+rd)|([\d]+th)"
    )

    matched_address = re.search(address_regex_pattern, address)

    if not matched_address:
        return address.title().strip()

    formatted_address = [
        a.title() if a != matched_address.group() else a
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
