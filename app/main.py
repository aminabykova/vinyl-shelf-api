"""Vinyl Shelf API - рабочая заглушка по схеме openapi.yaml.

Внешние системы и другие сервисы заменены упрощённой логикой в памяти:
Discogs и каталог - словарь в app/store.py, уведомления - журнал в памяти.
"""
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, Path, Query, Response

from . import store as db
from .auth import current_user_id
from .errors import (ApiError, bad_request, conflict, forbidden, not_found,
                     register_error_handlers)
from .schemas import (CollectionItem, CreateCollectionItemRequest, CreateListingRequest,
                      CreateReviewRequest, CreateWantlistRequest, Error, Listing, Release,
                      ReleaseList, Review, UpdateCollectionItemRequest, UpdateReviewRequest,
                      WantlistEntry)

app = FastAPI(
    title="Vinyl Shelf API",
    version="1.0.0",
    description=(
        "Рабочая заглушка API сервиса цифровой коллекции виниловых пластинок.\n\n"
        "Авторизация: нажмите Authorize и введите токен `user-1` (или `user-2`, `user-3`...). "
        "Число в токене - идентификатор пользователя."
    ),
)
register_error_handlers(app)

api = APIRouter(prefix="/api/v1")

ERR = {"model": Error}
AUTH_ERRORS = {401: {**ERR, "description": "Токен отсутствует или недействителен"}}
BARCODE_RE = r"^[0-9]{8,14}$"
IdPath = Path(ge=1, description="Идентификатор ресурса")


def _item_out(row: db.ItemRow) -> CollectionItem:
    return CollectionItem(id=row.id, releaseId=row.releaseId, status=row.status,
                          mediaCondition=row.mediaCondition, sleeveCondition=row.sleeveCondition,
                          note=row.note)


def _listing_out(row: db.ListingRow) -> Listing:
    return Listing(id=row.id, collectionItemId=row.collectionItemId, price=row.price,
                   currency=row.currency, status=row.status)


def _review_out(row: db.ReviewRow) -> Review:
    return Review(id=row.id, releaseId=row.releaseId, authorId=row.authorId,
                  pros=row.pros, cons=row.cons)


# ---------------------------------------------------------------- catalog
@api.get("/catalog/lookup", response_model=ReleaseList, tags=["catalog"],
         operation_id="lookupByBarcode", summary="Поиск релизов по штрихкоду",
         responses={**AUTH_ERRORS, 400: ERR, 404: ERR, 503: ERR})
def lookup_by_barcode(
    barcode: str = Query(description="Штрихкод, 8-14 цифр", pattern=BARCODE_RE, examples=["0602537284332"]),
    _: int = Depends(current_user_id),
):
    if barcode == db.DISCOGS_DOWN_BARCODE:
        raise ApiError(503, "EXTERNAL_UNAVAILABLE",
                       "Внешняя база временно недоступна, повторите запрос позже.")
    release_ids = db.BARCODES.get(barcode)
    if not release_ids:
        raise not_found("Релиз не найден. Добавьте пластинку вручную.")
    return ReleaseList(releases=[Release(**db.RELEASES[rid]) for rid in release_ids])


# ------------------------------------------------------------- collection
@api.post("/collection/items", response_model=CollectionItem, status_code=201, tags=["collection"],
          operation_id="createCollectionItem", summary="Создать черновик карточки в коллекции",
          responses={**AUTH_ERRORS, 400: ERR, 404: ERR})
def create_collection_item(body: CreateCollectionItemRequest, user_id: int = Depends(current_user_id)):
    if body.releaseId not in db.RELEASES:
        raise not_found("Релиз не найден.")
    row = db.ItemRow(id=db.store.next_id("item"), userId=user_id, releaseId=body.releaseId)
    db.store.items[row.id] = row
    return _item_out(row)


@api.patch("/collection/items/{id}", response_model=CollectionItem, tags=["collection"],
           operation_id="updateCollectionItem", summary="Дополнить и подтвердить карточку",
           responses={**AUTH_ERRORS, 400: ERR, 403: ERR, 404: ERR, 409: ERR})
def update_collection_item(body: UpdateCollectionItemRequest, id: int = IdPath,
                           user_id: int = Depends(current_user_id)):
    row = db.store.items.get(id)
    if row is None:
        raise not_found("Экземпляр не найден.")
    if row.userId != user_id:
        raise forbidden()
    if body.confirm:
        if row.status != "DRAFT":
            raise conflict("Подтвердить можно только черновик.")
        row.status = "IN_COLLECTION"
    if body.mediaCondition is not None:
        row.mediaCondition = body.mediaCondition
    if body.sleeveCondition is not None:
        row.sleeveCondition = body.sleeveCondition
    if body.note is not None:
        row.note = body.note
    return _item_out(row)


@api.post("/collection/wantlist", response_model=WantlistEntry, status_code=201, tags=["collection"],
          operation_id="addToWantlist", summary="Добавить релиз в Wantlist",
          responses={**AUTH_ERRORS, 400: ERR, 404: ERR, 409: ERR})
def add_to_wantlist(body: CreateWantlistRequest, user_id: int = Depends(current_user_id)):
    if body.releaseId not in db.RELEASES:
        raise not_found("Релиз не найден.")
    if any(w.userId == user_id and w.releaseId == body.releaseId for w in db.store.wantlist.values()):
        raise conflict("Релиз уже добавлен в Wantlist.")
    row = db.WantRow(id=db.store.next_id("want"), userId=user_id, releaseId=body.releaseId,
                     notify=body.notify)
    db.store.wantlist[row.id] = row
    return WantlistEntry(id=row.id, releaseId=row.releaseId, notify=row.notify)


@api.delete("/collection/wantlist/{id}", status_code=204, tags=["collection"],
            operation_id="removeFromWantlist", summary="Удалить релиз из Wantlist",
            responses={**AUTH_ERRORS, 403: ERR, 404: ERR})
def remove_from_wantlist(id: int = IdPath, user_id: int = Depends(current_user_id)):
    row = db.store.wantlist.get(id)
    if row is None:
        raise not_found("Запись Wantlist не найдена.")
    if row.userId != user_id:
        raise forbidden()
    del db.store.wantlist[id]
    return Response(status_code=204)


# ------------------------------------------------------------ marketplace
def _notify_wantlist(listing: db.ListingRow, item: db.ItemRow) -> None:
    """Заглушка цепочки ListingCreated -> Notification -> Push / Email.

    Находит записи Wantlist с этим релизом и включёнными уведомлениями,
    кроме самого продавца, и пишет "отправленные" уведомления в журнал.
    """
    release = db.RELEASES[item.releaseId]
    for want in db.store.wantlist.values():
        if want.releaseId == item.releaseId and want.notify and want.userId != listing.sellerId:
            db.store.notifications.append({
                "userId": want.userId,
                "listingId": listing.id,
                "text": (f"В продаже релиз из вашего Wantlist: {release['artist']} - "
                         f"{release['title']}, {listing.price:g} {listing.currency}"),
                "link": f"vinylshelf://listings/{listing.id}",
            })


@api.post("/marketplace/listings", response_model=Listing, status_code=201, tags=["marketplace"],
          operation_id="createListing", summary="Выставить экземпляр на продажу",
          responses={**AUTH_ERRORS, 400: ERR, 403: ERR, 404: ERR, 409: ERR})
def create_listing(body: CreateListingRequest, user_id: int = Depends(current_user_id)):
    item = db.store.items.get(body.collectionItemId)
    if item is None:
        raise not_found("Экземпляр не найден.")
    if item.userId != user_id:
        raise forbidden()
    if item.status != "IN_COLLECTION":
        raise conflict("Экземпляр нельзя выставить на продажу в текущем статусе.")
    # В боевой системе Marketplace просит Collection сменить статус; здесь это один шаг.
    item.status = "ON_SALE"
    row = db.ListingRow(id=db.store.next_id("listing"), collectionItemId=item.id, sellerId=user_id,
                        price=body.price, currency=body.currency)
    db.store.listings[row.id] = row
    _notify_wantlist(row, item)
    return _listing_out(row)


@api.delete("/marketplace/listings/{id}", status_code=204, tags=["marketplace"],
            operation_id="cancelListing", summary="Снять лот с продажи",
            responses={**AUTH_ERRORS, 403: ERR, 404: ERR, 409: ERR})
def cancel_listing(id: int = IdPath, user_id: int = Depends(current_user_id)):
    row = db.store.listings.get(id)
    if row is None:
        raise not_found("Лот не найден.")
    if row.sellerId != user_id:
        raise forbidden()
    if row.status != "ACTIVE":
        raise conflict("Лот нельзя снять, он уже не активен.")
    row.status = "CANCELLED"
    db.store.items[row.collectionItemId].status = "IN_COLLECTION"
    return Response(status_code=204)


# ----------------------------------------------------------------- social
def _has_release(user_id: int, release_id: int) -> bool:
    """Релиз есть у пользователя: экземпляр в коллекции или на продаже (не черновик)."""
    return any(i.userId == user_id and i.releaseId == release_id
               and i.status in ("IN_COLLECTION", "ON_SALE") for i in db.store.items.values())


def _check_review_text(pros: Optional[str], cons: Optional[str]) -> None:
    if not (pros and pros.strip()) and not (cons and cons.strip()):
        raise bad_request("Заполните хотя бы одно из полей «Плюсы» или «Минусы».")


@api.post("/social/reviews", response_model=Review, status_code=201, tags=["social"],
          operation_id="createReview", summary="Оставить ревью на релиз",
          responses={**AUTH_ERRORS, 400: ERR, 403: ERR, 409: ERR})
def create_review(body: CreateReviewRequest, user_id: int = Depends(current_user_id)):
    _check_review_text(body.pros, body.cons)
    if not _has_release(user_id, body.releaseId):
        raise ApiError(403, "FORBIDDEN", "Ревью можно оставить только на релиз из вашей коллекции.")
    if any(r.authorId == user_id and r.releaseId == body.releaseId for r in db.store.reviews.values()):
        raise conflict("Вы уже оставили ревью на этот релиз.")
    row = db.ReviewRow(id=db.store.next_id("review"), releaseId=body.releaseId, authorId=user_id,
                       pros=body.pros, cons=body.cons)
    db.store.reviews[row.id] = row
    return _review_out(row)


@api.patch("/social/reviews/{id}", response_model=Review, tags=["social"],
           operation_id="updateReview", summary="Изменить своё ревью",
           responses={**AUTH_ERRORS, 400: ERR, 403: ERR, 404: ERR})
def update_review(body: UpdateReviewRequest, id: int = IdPath, user_id: int = Depends(current_user_id)):
    row = db.store.reviews.get(id)
    if row is None:
        raise not_found("Ревью не найдено.")
    if row.authorId != user_id:
        raise forbidden()
    pros = body.pros if body.pros is not None else row.pros
    cons = body.cons if body.cons is not None else row.cons
    _check_review_text(pros, cons)
    row.pros, row.cons = pros, cons
    return _review_out(row)


app.include_router(api)


# ------------------------------------------- служебные эндпоинты заглушки
@app.get("/debug/notifications", include_in_schema=False)
def debug_notifications():
    """Журнал уведомлений, "отправленных" заглушкой Notification Service."""
    return {"notifications": db.store.notifications}


@app.post("/debug/reset", include_in_schema=False, status_code=204)
def debug_reset():
    """Очистить все данные заглушки."""
    db.reset()
    return Response(status_code=204)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}
