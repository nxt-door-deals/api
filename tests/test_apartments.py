from app.main import app
from routers import apartments
from fastapi.testclient import TestClient

app.include_router(apartments.router)
client = TestClient(app)


# def test_get_apartments():
#     res = client.get("/apartments/all")
#     assert res.status_code == 200
#     assert res is not None


def test_aparment_search():
    res = client.get("/apartments/search/?name={rep}")
    assert res.status_code == 200


def test_add_apartment():
    res = client.post(
        "/apartments/add",
        json={
            "name": "Republic Of Whitefield",
            "address1": "EPIP Zone",
            "address2": "Whitefield",
            "city": "Bengaluru",
            "state": "Karnataka",
            "pincode": "560066",
        },
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 201
    assert res.json()["name"].title() == "Republic Of Whitefield"
