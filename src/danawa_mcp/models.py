"""Pydantic data models for Danawa entities."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Category(BaseModel):
    """A Danawa product category."""

    id: str
    name: str
    parent_id: str | None = None
    url: str | None = None
    child_count: int = 0
    depth: int = 0


class FilterOption(BaseModel):
    """A single selectable option within a filter group."""

    value: str
    label: str
    count: int = 0
    checked: bool = False


class FilterGroup(BaseModel):
    """A group of related filter options (e.g., Brand, CPU, RAM)."""

    key: str
    name: str
    options: list[FilterOption] = Field(default_factory=list)
    multi_select: bool = True


class ProductSummary(BaseModel):
    """Lightweight product info used in list/search results."""

    id: str
    name: str
    price: int | None = None
    image_url: str | None = None
    shop_count: int = 0
    rating: float | None = None
    review_count: int = 0
    url: str | None = None
    category_name: str | None = None


class ProductSpec(BaseModel):
    """A single specification entry (name → value)."""

    name: str
    value: str


class ProductDetail(BaseModel):
    """Full product detail including specs and images."""

    id: str
    name: str
    brand: str | None = None
    category: str | None = None
    price: int | None = None
    description: str | None = None
    specs: list[ProductSpec] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    detail_image_urls: list[str] = Field(default_factory=list)
    rating: float | None = None
    review_count: int = 0
    url: str | None = None


class Review(BaseModel):
    """A single user review for a product."""

    id: str | None = None
    author: str | None = None
    date: str | None = None
    rating: int | None = None
    title: str | None = None
    content: str
    helpful_count: int = 0
    product_name: str | None = None


class ReviewSummary(BaseModel):
    """Aggregated review statistics for a product."""

    product_id: str
    total_count: int = 0
    average_rating: float | None = None
    rating_distribution: dict[int, int] = Field(default_factory=dict)


class ProductListResult(BaseModel):
    """Paginated product listing with applied filters."""

    category_id: str | None = None
    query: str | None = None
    total_count: int = 0
    page: int = 1
    per_page: int = 20
    products: list[ProductSummary] = Field(default_factory=list)
    filter_groups: list[FilterGroup] = Field(default_factory=list)


class ReviewListResult(BaseModel):
    """Paginated review listing."""

    product_id: str
    total_count: int = 0
    page: int = 1
    per_page: int = 20
    reviews: list[Review] = Field(default_factory=list)
    summary: ReviewSummary | None = None


class NetworkResponse(BaseModel):
    """A captured JSON response from Danawa's internal API."""

    url: str
    status: int
    data: object
