"""Хранилище в памяти и тестовые данные (заглушка вместо PostgreSQL, Redis и Discogs)."""
from dataclasses import dataclass, field
from itertools import count
from typing import Optional


@dataclass
class ItemRow:
    id: int
    userId: int
    releaseId: int
    status: str = "DRAFT"
    mediaCondition: Optional[str] = None
    sleeveCondition: Optional[str] = None
    note: Optional[str] = None


@dataclass
class ListingRow:
    id: int
    collectionItemId: int
    sellerId: int
    price: float
    currency: str
    status: str = "ACTIVE"


@dataclass
class ReviewRow:
    id: int
    releaseId: int
    authorId: int
    pros: Optional[str]
    cons: Optional[str]


@dataclass
class WantRow:
    id: int
    userId: int
    releaseId: int
    notify: bool = True


# Релизы, которые "знает" каталог (в боевой системе это таблица release + ответы Discogs).
RELEASES: dict[int, dict] = {
    1001: dict(releaseId=1001, artist="Pink Floyd", title="The Dark Side of the Moon", year=1973,
               label="Harvest", country="UK", genres=["Rock"],
               tracklist=["Speak to Me", "Breathe", "On the Run"]),
    1002: dict(releaseId=1002, artist="Pink Floyd", title="The Dark Side of the Moon", year=2016,
               label="Pink Floyd Records", country="EU", genres=["Rock"], tracklist=None),
    1003: dict(releaseId=1003, artist="Miles Davis", title="Kind of Blue", year=1959,
               label="Columbia", country="US", genres=["Jazz"],
               tracklist=["So What", "Freddie Freeloader", "Blue in Green"]),
    1004: dict(releaseId=1004, artist="Daft Punk", title="Random Access Memories", year=2013,
               label="Columbia", country="EU", genres=["Electronic"], tracklist=None),
}

# Штрихкод -> релизы. Один штрихкод может вести к нескольким релизам.
BARCODES: dict[str, list[int]] = {
    "0602537284332": [1001, 1002],
    "5099902988627": [1003],
    "0888837000000": [1004],
}

# Штрихкод, на котором заглушка имитирует недоступность Discogs (ответ 503).
DISCOGS_DOWN_BARCODE = "0000000000000"


@dataclass
class Store:
    items: dict[int, ItemRow] = field(default_factory=dict)
    listings: dict[int, ListingRow] = field(default_factory=dict)
    reviews: dict[int, ReviewRow] = field(default_factory=dict)
    wantlist: dict[int, WantRow] = field(default_factory=dict)
    # Журнал отправленных "уведомлений" (заглушка Notification Service и Push / Email провайдера).
    notifications: list[dict] = field(default_factory=list)
    _ids: dict[str, count] = field(default_factory=dict)

    def next_id(self, name: str) -> int:
        if name not in self._ids:
            self._ids[name] = count(1)
        return next(self._ids[name])


store = Store()


def reset() -> None:
    """Сбросить данные (для тестов и ручной проверки с чистого листа)."""
    global store
    fresh = Store()
    store.items, store.listings, store.reviews = fresh.items, fresh.listings, fresh.reviews
    store.wantlist, store.notifications, store._ids = fresh.wantlist, fresh.notifications, fresh._ids
