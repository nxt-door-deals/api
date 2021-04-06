import datetime

from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from sentry_sdk import capture_exception
from sqlalchemy import cast
from sqlalchemy import Date
from sqlalchemy.orm import Session

from . import get_db
from database.models import Metric


class Counts:
    def __init__(self):
        self.metric_record = None

    def check_metric_record(self, db: Session = Depends(get_db)):
        metric_record_dict = {}

        self.metric_record = (
            db.query(Metric)
            .filter(cast(Metric.date, Date) == datetime.date.today())
            .first()
        )

        if not self.metric_record:
            new_metric_record = Metric(
                date=datetime.date.today(),
                registered_users=0,
                deleted_user_accounts=0,
                ads_posted=0,
                items_sold=0,
                ads_reported=0,
                apartments_registered=0,
            )

            try:
                db.add(new_metric_record)

                db.commit()

                metric_record_dict["id"] = new_metric_record.id
                metric_record_dict[
                    "registered_users"
                ] = new_metric_record.registered_users
                metric_record_dict[
                    "deleted_user_accounts"
                ] = new_metric_record.deleted_user_accounts
                metric_record_dict["ads_posted"] = new_metric_record.ads_posted
                metric_record_dict["items_sold"] = new_metric_record.items_sold
                metric_record_dict[
                    "ads_reported"
                ] = new_metric_record.ads_reported
                metric_record_dict[
                    "apartments_registered"
                ] = new_metric_record.apartments_registered
            except Exception as e:
                capture_exception(e)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            metric_record_dict["id"] = self.metric_record.id
            metric_record_dict[
                "registered_users"
            ] = self.metric_record.registered_users
            metric_record_dict[
                "deleted_user_accounts"
            ] = self.metric_record.deleted_user_accounts
            metric_record_dict["ads_posted"] = self.metric_record.ads_posted
            metric_record_dict["items_sold"] = self.metric_record.items_sold
            metric_record_dict["ads_reported"] = self.metric_record.ads_reported
            metric_record_dict[
                "apartments_registered"
            ] = self.metric_record.apartments_registered

        return metric_record_dict

    def increment_registered_users(self, db: Session = Depends(get_db)):
        record = self.check_metric_record(db)

        db.query(Metric).filter(Metric.id == record["id"]).update(
            {Metric.registered_users: record["registered_users"] + 1}
        )

        db.commit()

    def increment_deleted_user_accounts(self, db: Session = Depends(get_db)):
        record = self.check_metric_record(db)

        db.query(Metric).filter(Metric.id == record["id"]).update(
            {Metric.deleted_user_accounts: record["deleted_user_accounts"] + 1}
        )

        db.commit()

    def increment_posted_ad_counts(self, db: Session = Depends(get_db)):
        record = self.check_metric_record(db)

        db.query(Metric).filter(Metric.id == record["id"]).update(
            {Metric.ads_posted: record["ads_posted"] + 1}
        )

        db.commit()

    def increment_items_sold(self, db: Session = Depends(get_db)):
        record = self.check_metric_record(db)

        db.query(Metric).filter(Metric.id == record["id"]).update(
            {Metric.items_sold: record["items_sold"] + 1}
        )

        db.commit()

    def increment_ads_reported(self, db: Session = Depends(get_db)):
        record = self.check_metric_record(db)

        db.query(Metric).filter(Metric.id == record["id"]).update(
            {Metric.ads_reported: record["ads_reported"] + 1}
        )

        db.commit()

    def increment_apartments_registered(self, db: Session = Depends(get_db)):
        record = self.check_metric_record(db)

        db.query(Metric).filter(Metric.id == record["id"]).update(
            {Metric.apartments_registered: record["apartments_registered"] + 1}
        )

        db.commit()


metric_counts = Counts()
