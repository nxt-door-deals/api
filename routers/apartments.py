from fastapi import APIRouter

router = APIRouter()


@router.get("/api/v1/apartments")
async def get_apartments():
    return {"apartment": "some apartment"}
