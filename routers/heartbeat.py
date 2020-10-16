from . import router
from fastapi import status


@router.get("/heartbeat")
def return_heartbeat():
    return status.HTTP_200_OK
