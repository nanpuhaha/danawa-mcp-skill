"""Unit tests for danawa_mcp.models (no network required)."""

from __future__ import annotations

import pytest

from danawa_mcp.models import (
    Category,
    FilterGroup,
    FilterOption,
    ProductDetail,
    ProductListResult,
    ProductSpec,
    ProductSummary,
    Review,
    ReviewListResult,
    ReviewSummary,
)


class TestCategory:
    def test_minimal(self):
        cat = Category(id="10228", name="노트북")
        assert cat.id == "10228"
        assert cat.name == "노트북"
        assert cat.parent_id is None
        assert cat.child_count == 0
        assert cat.depth == 0

    def test_with_parent(self):
        cat = Category(id="10229", name="울트라북", parent_id="10228", depth=1)
        assert cat.parent_id == "10228"
        assert cat.depth == 1


class TestFilterOption:
    def test_defaults(self):
        opt = FilterOption(value="samsung", label="삼성전자")
        assert opt.checked is False
        assert opt.count == 0

    def test_with_count(self):
        opt = FilterOption(value="lg", label="LG전자", count=35, checked=True)
        assert opt.count == 35
        assert opt.checked is True


class TestFilterGroup:
    def test_empty(self):
        group = FilterGroup(key="brand", name="브랜드")
        assert group.options == []
        assert group.multi_select is True

    def test_with_options(self):
        options = [
            FilterOption(value="samsung", label="삼성전자", count=45),
            FilterOption(value="lg", label="LG전자", count=38),
        ]
        group = FilterGroup(key="brand", name="브랜드", options=options)
        assert len(group.options) == 2
        assert group.options[0].value == "samsung"


class TestProductSummary:
    def test_minimal(self):
        p = ProductSummary(id="16960793", name="삼성 갤럭시북")
        assert p.price is None
        assert p.shop_count == 0
        assert p.review_count == 0

    def test_full(self):
        p = ProductSummary(
            id="16960793",
            name="삼성 갤럭시북",
            price=1_990_000,
            shop_count=12,
            rating=4.5,
            review_count=42,
            url="https://prod.danawa.com/info/?pcode=16960793",
        )
        assert p.price == 1_990_000
        assert p.rating == pytest.approx(4.5)


class TestProductDetail:
    def test_minimal(self):
        d = ProductDetail(id="16960793", name="삼성 갤럭시북")
        assert d.specs == []
        assert d.image_urls == []

    def test_with_specs(self):
        specs = [
            ProductSpec(name="CPU", value="Intel i7-1360P"),
            ProductSpec(name="RAM", value="16GB"),
        ]
        d = ProductDetail(id="abc", name="테스트 노트북", specs=specs)
        assert len(d.specs) == 2
        assert d.specs[0].name == "CPU"


class TestReview:
    def test_minimal(self):
        r = Review(content="좋아요!")
        assert r.rating is None
        assert r.helpful_count == 0

    def test_full(self):
        r = Review(
            id="1001",
            author="hong**",
            date="2024-03-15",
            rating=5,
            title="정말 좋아요",
            content="배터리가 오래 갑니다.",
            helpful_count=12,
        )
        assert r.rating == 5
        assert r.helpful_count == 12


class TestReviewListResult:
    def test_empty(self):
        result = ReviewListResult(product_id="16960793")
        assert result.reviews == []
        assert result.total_count == 0
        assert result.summary is None

    def test_with_summary(self):
        summary = ReviewSummary(
            product_id="16960793",
            total_count=42,
            average_rating=4.5,
        )
        result = ReviewListResult(
            product_id="16960793",
            total_count=42,
            reviews=[Review(content="좋아요")],
            summary=summary,
        )
        assert result.summary is not None
        assert result.summary.average_rating == pytest.approx(4.5)


class TestProductListResult:
    def test_defaults(self):
        r = ProductListResult()
        assert r.total_count == 0
        assert r.page == 1
        assert r.per_page == 20
        assert r.products == []
        assert r.filter_groups == []

    def test_with_products(self):
        products = [
            ProductSummary(id="1", name="제품1"),
            ProductSummary(id="2", name="제품2"),
        ]
        r = ProductListResult(
            category_id="10228",
            total_count=2,
            products=products,
        )
        assert len(r.products) == 2
        assert r.category_id == "10228"
