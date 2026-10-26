"""Тесты API: запускают запросы к приложению и проверяют ответы."""
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import app
from app.store import reset

U1 = {"Authorization": "Bearer user-1"}  # продавец и автор
U2 = {"Authorization": "Bearer user-2"}  # подписчик
BARCODE = "0602537284332"  # два релиза: 1001 и 1002


@pytest.fixture(autouse=True)
def clean_state():
    reset()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def make_item(client, user=U1, release_id=1001, confirm=True):
    r = client.post("/api/v1/collection/items", json={"releaseId": release_id}, headers=user)
    assert r.status_code == 201
    item = r.json()
    if confirm:
        r = client.patch(f"/api/v1/collection/items/{item['id']}", json={"confirm": True}, headers=user)
        assert r.status_code == 200
        item = r.json()
    return item


# ------------------------------------------------------------ авторизация
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic abc"}])
def test_requires_valid_token(client, headers):
    r = client.get("/api/v1/catalog/lookup", params={"barcode": BARCODE}, headers=headers)
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------- каталог
def test_lookup_returns_list_of_releases(client):
    r = client.get("/api/v1/catalog/lookup", params={"barcode": BARCODE}, headers=U1)
    assert r.status_code == 200
    releases = r.json()["releases"]
    assert [x["releaseId"] for x in releases] == [1001, 1002]
    assert releases[1]["tracklist"] is None


@pytest.mark.parametrize("barcode", ["123", "abcdefgh12", "123456789012345"])
def test_lookup_rejects_bad_barcode(client, barcode):
    r = client.get("/api/v1/catalog/lookup", params={"barcode": barcode}, headers=U1)
    assert r.status_code == 400
    assert r.json()["code"] == "BAD_REQUEST"


def test_lookup_without_barcode_is_400(client):
    assert client.get("/api/v1/catalog/lookup", headers=U1).status_code == 400


def test_lookup_not_found(client):
    r = client.get("/api/v1/catalog/lookup", params={"barcode": "1111111111111"}, headers=U1)
    assert r.status_code == 404
    assert "вручную" in r.json()["message"]


def test_lookup_discogs_unavailable(client):
    r = client.get("/api/v1/catalog/lookup", params={"barcode": "0000000000000"}, headers=U1)
    assert r.status_code == 503
    assert r.json()["code"] == "EXTERNAL_UNAVAILABLE"


# ------------------------------------------------------------- коллекция
def test_create_item_is_draft_then_confirm(client):
    item = make_item(client, confirm=False)
    assert item["status"] == "DRAFT"
    r = client.patch(f"/api/v1/collection/items/{item['id']}", headers=U1, json={
        "mediaCondition": "NM", "sleeveCondition": "VG+", "note": "Первый пресс", "confirm": True})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "IN_COLLECTION"
    assert (body["mediaCondition"], body["sleeveCondition"], body["note"]) == ("NM", "VG+", "Первый пресс")


def test_create_item_unknown_release(client):
    r = client.post("/api/v1/collection/items", json={"releaseId": 99999}, headers=U1)
    assert r.status_code == 404


def test_create_item_bad_body(client):
    assert client.post("/api/v1/collection/items", json={"releaseId": "x"}, headers=U1).status_code == 400
    assert client.post("/api/v1/collection/items", json={}, headers=U1).status_code == 400


def test_update_item_errors(client):
    item = make_item(client)
    url = f"/api/v1/collection/items/{item['id']}"
    assert client.patch(url, json={"mediaCondition": "ZZ"}, headers=U1).status_code == 400
    assert client.patch(url, json={"note": "x"}, headers=U2).status_code == 403
    assert client.patch("/api/v1/collection/items/9999", json={"note": "x"}, headers=U1).status_code == 404
    # повторное подтверждение уже подтверждённого экземпляра
    assert client.patch(url, json={"confirm": True}, headers=U1).status_code == 409


# ------------------------------------------------------------ маркетплейс
def test_create_and_cancel_listing(client):
    item = make_item(client)
    r = client.post("/api/v1/marketplace/listings", headers=U1,
                    json={"collectionItemId": item["id"], "price": 4500, "currency": "RUB"})
    assert r.status_code == 201
    listing = r.json()
    assert listing["status"] == "ACTIVE" and listing["price"] == 4500

    item_url = f"/api/v1/collection/items/{item['id']}"
    # экземпляр на продаже: подтвердить повторно нельзя, статус ON_SALE
    assert client.patch(item_url, json={"note": "n"}, headers=U1).json()["status"] == "ON_SALE"

    assert client.delete(f"/api/v1/marketplace/listings/{listing['id']}", headers=U1).status_code == 204
    assert client.patch(item_url, json={"note": "n"}, headers=U1).json()["status"] == "IN_COLLECTION"
    # повторное снятие
    assert client.delete(f"/api/v1/marketplace/listings/{listing['id']}", headers=U1).status_code == 409


def test_listing_validation(client):
    item = make_item(client)
    url = "/api/v1/marketplace/listings"
    ok = {"collectionItemId": item["id"], "price": 100, "currency": "RUB"}
    assert client.post(url, json={**ok, "price": 0}, headers=U1).status_code == 400
    assert client.post(url, json={**ok, "price": -5}, headers=U1).status_code == 400
    assert client.post(url, json={**ok, "currency": "GBP"}, headers=U1).status_code == 400
    assert client.post(url, json={**ok, "collectionItemId": 9999}, headers=U1).status_code == 404
    assert client.post(url, json=ok, headers=U2).status_code == 403


def test_cannot_list_draft_or_already_listed_item(client):
    draft = make_item(client, confirm=False)
    body = {"collectionItemId": draft["id"], "price": 100, "currency": "USD"}
    assert client.post("/api/v1/marketplace/listings", json=body, headers=U1).status_code == 409

    item = make_item(client)
    body["collectionItemId"] = item["id"]
    assert client.post("/api/v1/marketplace/listings", json=body, headers=U1).status_code == 201
    r = client.post("/api/v1/marketplace/listings", json=body, headers=U1)
    assert r.status_code == 409
    assert r.json()["code"] == "CONFLICT"


def test_cancel_listing_errors(client):
    item = make_item(client)
    listing = client.post("/api/v1/marketplace/listings", headers=U1,
                          json={"collectionItemId": item["id"], "price": 10, "currency": "EUR"}).json()
    assert client.delete(f"/api/v1/marketplace/listings/{listing['id']}", headers=U2).status_code == 403
    assert client.delete("/api/v1/marketplace/listings/9999", headers=U1).status_code == 404


# --------------------------------------------------------------- wantlist
def test_wantlist_add_duplicate_delete(client):
    r = client.post("/api/v1/collection/wantlist", json={"releaseId": 1002}, headers=U2)
    assert r.status_code == 201
    entry = r.json()
    assert entry["notify"] is True
    assert client.post("/api/v1/collection/wantlist", json={"releaseId": 1002}, headers=U2).status_code == 409
    assert client.post("/api/v1/collection/wantlist", json={"releaseId": 5}, headers=U2).status_code == 404
    assert client.delete(f"/api/v1/collection/wantlist/{entry['id']}", headers=U1).status_code == 403
    assert client.delete(f"/api/v1/collection/wantlist/{entry['id']}", headers=U2).status_code == 204
    assert client.delete(f"/api/v1/collection/wantlist/{entry['id']}", headers=U2).status_code == 404


def test_notification_flow_for_wantlist(client):
    """Сценарий UC-2: подписчик получает уведомление, продавец и отключившие - нет."""
    client.post("/api/v1/collection/wantlist", json={"releaseId": 1001}, headers=U2)
    client.post("/api/v1/collection/wantlist", json={"releaseId": 1001, "notify": False},
                headers={"Authorization": "Bearer user-3"})
    client.post("/api/v1/collection/wantlist", json={"releaseId": 1001}, headers=U1)  # сам продавец
    item = make_item(client, release_id=1001)
    r = client.post("/api/v1/marketplace/listings", headers=U1,
                    json={"collectionItemId": item["id"], "price": 4500, "currency": "RUB"})
    assert r.status_code == 201

    sent = client.get("/debug/notifications").json()["notifications"]
    assert [n["userId"] for n in sent] == [2]
    assert sent[0]["listingId"] == r.json()["id"]
    assert "Pink Floyd" in sent[0]["text"] and "4500 RUB" in sent[0]["text"]


def test_no_notification_for_other_release(client):
    client.post("/api/v1/collection/wantlist", json={"releaseId": 1002}, headers=U2)
    item = make_item(client, release_id=1001)
    client.post("/api/v1/marketplace/listings", headers=U1,
                json={"collectionItemId": item["id"], "price": 1, "currency": "USD"})
    assert client.get("/debug/notifications").json()["notifications"] == []


# ----------------------------------------------------------------- ревью
def test_review_requires_release_in_collection(client):
    body = {"releaseId": 1001, "pros": "Бас"}
    assert client.post("/api/v1/social/reviews", json=body, headers=U1).status_code == 403
    make_item(client, confirm=False)  # черновик не считается
    assert client.post("/api/v1/social/reviews", json=body, headers=U1).status_code == 403
    make_item(client)
    assert client.post("/api/v1/social/reviews", json=body, headers=U1).status_code == 201


def test_review_unique_and_validation(client):
    make_item(client)
    url = "/api/v1/social/reviews"
    assert client.post(url, json={"releaseId": 1001}, headers=U1).status_code == 400
    assert client.post(url, json={"releaseId": 1001, "pros": "  "}, headers=U1).status_code == 400
    assert client.post(url, json={"releaseId": 1001, "pros": "x" * 3001}, headers=U1).status_code == 400
    assert client.post(url, json={"releaseId": 1001, "cons": "Шум"}, headers=U1).status_code == 201
    assert client.post(url, json={"releaseId": 1001, "pros": "Бас"}, headers=U1).status_code == 409


def test_review_update(client):
    make_item(client)
    review = client.post("/api/v1/social/reviews", headers=U1,
                         json={"releaseId": 1001, "pros": "Бас", "cons": "Шум"}).json()
    url = f"/api/v1/social/reviews/{review['id']}"
    r = client.patch(url, json={"cons": "Шум пропал после чистки"}, headers=U1)
    assert r.status_code == 200
    assert r.json()["pros"] == "Бас" and r.json()["cons"] == "Шум пропал после чистки"
    assert client.patch(url, json={"cons": "x"}, headers=U2).status_code == 403
    assert client.patch("/api/v1/social/reviews/9999", json={"cons": "x"}, headers=U1).status_code == 404
    # нельзя оставить ревью совсем без текста
    assert client.patch(url, json={"pros": "", "cons": ""}, headers=U1).status_code == 400


# ------------------------------------------------------ схема и контракт
def test_all_paths_from_openapi_yaml_are_implemented(client):
    """Каждая пара «путь + метод» из openapi.yaml должна быть в работающем приложении."""
    spec = yaml.safe_load((Path(__file__).parent.parent / "openapi.yaml").read_text(encoding="utf-8"))
    live = app.openapi()["paths"]
    for path, ops in spec["paths"].items():
        full = "/api/v1" + path
        assert full in live, f"нет пути {full}"
        for method in ops:
            assert method in live[full], f"нет метода {method.upper()} {full}"


def test_swagger_ui_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
