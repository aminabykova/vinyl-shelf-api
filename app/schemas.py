"""Модели запросов и ответов. Названия полей совпадают с openapi.yaml."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Currency = Literal["RUB", "USD", "EUR"]
Condition = Literal["M", "NM", "VG+", "VG", "G", "F", "P"]
ItemStatus = Literal["DRAFT", "IN_COLLECTION", "ON_SALE", "SOLD", "SHIPPED"]
ListingStatus = Literal["ACTIVE", "CANCELLED", "SOLD"]


class Error(BaseModel):
    code: str
    message: str


class Release(BaseModel):
    releaseId: int
    artist: str
    title: str
    year: Optional[int] = None
    label: Optional[str] = None
    country: Optional[str] = None
    genres: list[str] = []
    tracklist: Optional[list[str]] = None


class ReleaseList(BaseModel):
    releases: list[Release]


class CreateCollectionItemRequest(BaseModel):
    releaseId: int


class UpdateCollectionItemRequest(BaseModel):
    mediaCondition: Optional[Condition] = None
    sleeveCondition: Optional[Condition] = None
    note: Optional[str] = Field(default=None, max_length=1000)
    confirm: Optional[bool] = None


class CollectionItem(BaseModel):
    id: int
    releaseId: int
    status: ItemStatus
    mediaCondition: Optional[Condition] = None
    sleeveCondition: Optional[Condition] = None
    note: Optional[str] = None


class CreateListingRequest(BaseModel):
    collectionItemId: int
    price: float = Field(gt=0, le=99999999.99)
    currency: Currency


class Listing(BaseModel):
    id: int
    collectionItemId: int
    price: float
    currency: Currency
    status: ListingStatus


class CreateReviewRequest(BaseModel):
    releaseId: int
    pros: Optional[str] = Field(default=None, max_length=3000)
    cons: Optional[str] = Field(default=None, max_length=3000)


class UpdateReviewRequest(BaseModel):
    pros: Optional[str] = Field(default=None, max_length=3000)
    cons: Optional[str] = Field(default=None, max_length=3000)


class Review(BaseModel):
    id: int
    releaseId: int
    authorId: int
    pros: Optional[str] = None
    cons: Optional[str] = None


class CreateWantlistRequest(BaseModel):
    releaseId: int
    notify: bool = True


class WantlistEntry(BaseModel):
    id: int
    releaseId: int
    notify: bool
