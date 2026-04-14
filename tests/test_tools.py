"""Unit tests for tool-layer JSON parsers (no network / browser required).

These tests exercise the *parsing* functions in isolation by passing pre-built
fixture data, so they run quickly without Playwright.
"""

from __future__ import annotations

import pytest

from danawa_mcp.tools.categories import (
    _parse_categories_from_html,
    _parse_categories_from_json,
)
from danawa_mcp.tools.products import (
    _html_to_filters,
    _html_to_products,
    _json_to_filters,
    _json_to_products,
    _json_to_total,
)
from danawa_mcp.tools.reviews import (
    _parse_reviews_from_json,
    _parse_summary_from_json,
)

# ---------------------------------------------------------------------------
# Category parsers
# ---------------------------------------------------------------------------


class TestParseCategoriesFromJson:
    def test_returns_categories(self, sample_category_json):
        cats = _parse_categories_from_json(sample_category_json)
        assert len(cats) == 3
        ids = {c.id for c in cats}
        assert "10225" in ids
        assert "10231" in ids

    def test_parent_preserved(self, sample_category_json):
        cats = _parse_categories_from_json(sample_category_json)
        child = next(c for c in cats if c.id == "10231")
        assert child.parent_id == "10228"

    def test_url_generated(self, sample_category_json):
        cats = _parse_categories_from_json(sample_category_json)
        for cat in cats:
            assert cat.url is not None
            assert cat.id in cat.url

    def test_not_a_list_returns_empty(self):
        assert _parse_categories_from_json({"key": "value"}) == []
        assert _parse_categories_from_json(None) == []
        assert _parse_categories_from_json("string") == []

    def test_missing_id_or_name_skipped(self):
        data = [
            {"cateCd": "", "cateName": "노트북"},  # empty id
            {"cateCd": "10228", "cateName": ""},  # empty name
            {"cateCd": "10229", "cateName": "태블릿"},  # valid
        ]
        cats = _parse_categories_from_json(data)
        assert len(cats) == 1
        assert cats[0].id == "10229"


class TestParseCategoriesFromHtml:
    def test_extracts_cate_links(self):
        html = """
        <ul>
          <li><a href="https://prod.danawa.com/list/?cate=10228">노트북</a></li>
          <li><a href="https://prod.danawa.com/list/?cate=10229">태블릿</a></li>
        </ul>
        """
        cats = _parse_categories_from_html(html)
        assert len(cats) == 2
        names = {c.name for c in cats}
        assert "노트북" in names
        assert "태블릿" in names

    def test_deduplicates_same_id(self):
        html = """
        <a href="?cate=10228">노트북</a>
        <a href="?cate=10228">노트북 더보기</a>
        """
        cats = _parse_categories_from_html(html)
        assert len(cats) == 1

    def test_no_links_returns_empty(self):
        cats = _parse_categories_from_html("<html><body>No categories</body></html>")
        assert cats == []


# ---------------------------------------------------------------------------
# Product parsers
# ---------------------------------------------------------------------------


class TestJsonToProducts:
    def test_parses_product_list(self, sample_product_json):
        products = _json_to_products(sample_product_json)
        assert len(products) == 2

    def test_price_parsed(self, sample_product_json):
        products = _json_to_products(sample_product_json)
        assert products[0].price == 1_990_000

    def test_image_url_scheme(self, sample_product_json):
        products = _json_to_products(sample_product_json)
        assert products[0].image_url is not None
        assert products[0].image_url.startswith("https://")

    def test_rating_as_float(self, sample_product_json):
        products = _json_to_products(sample_product_json)
        assert products[0].rating == pytest.approx(4.5)

    def test_empty_list_returns_empty(self):
        assert _json_to_products([]) == []
        assert _json_to_products({}) == []
        assert _json_to_products(None) == []

    def test_missing_id_or_name_skipped(self):
        data = [
            {"productCode": "", "productName": "테스트"},
            {"productCode": "123", "productName": ""},
            {"productCode": "456", "productName": "유효한 제품"},
        ]
        products = _json_to_products(data)
        assert len(products) == 1
        assert products[0].id == "456"

    def test_url_generated(self, sample_product_json):
        products = _json_to_products(sample_product_json)
        for p in products:
            assert p.url is not None
            assert p.id in p.url


class TestJsonToFilters:
    def test_parses_filter_groups(self, sample_filter_json):
        groups = _json_to_filters(sample_filter_json)
        assert len(groups) == 2

    def test_group_keys(self, sample_filter_json):
        groups = _json_to_filters(sample_filter_json)
        keys = {g.key for g in groups}
        assert "brand" in keys
        assert "cpu" in keys

    def test_options_parsed(self, sample_filter_json):
        groups = _json_to_filters(sample_filter_json)
        brand = next(g for g in groups if g.key == "brand")
        assert len(brand.options) == 3
        labels = {o.label for o in brand.options}
        assert "삼성전자" in labels

    def test_option_count(self, sample_filter_json):
        groups = _json_to_filters(sample_filter_json)
        brand = next(g for g in groups if g.key == "brand")
        samsung = next(o for o in brand.options if o.value == "samsung")
        assert samsung.count == 45

    def test_empty_returns_empty(self):
        assert _json_to_filters({}) == []
        assert _json_to_filters([]) == []


class TestJsonToTotal:
    def test_extracts_total_count(self, sample_product_json):
        assert _json_to_total(sample_product_json) == 2

    def test_returns_zero_on_missing(self):
        assert _json_to_total({}) == 0
        assert _json_to_total(None) == 0


class TestHtmlToProducts:
    def test_no_products_in_empty_html(self):
        assert _html_to_products("<html></html>") == []


class TestHtmlToFilters:
    def test_no_filters_in_empty_html(self):
        assert _html_to_filters("<html></html>") == []


# ---------------------------------------------------------------------------
# Review parsers
# ---------------------------------------------------------------------------


class TestParseReviewsFromJson:
    def test_parses_reviews(self, sample_review_json):
        reviews = _parse_reviews_from_json(sample_review_json)
        assert len(reviews) == 2

    def test_review_fields(self, sample_review_json):
        reviews = _parse_reviews_from_json(sample_review_json)
        r = reviews[0]
        assert r.id == "1001"
        assert r.author == "hong**"
        assert r.rating == 5
        assert r.title == "정말 좋아요"
        assert "배터리" in r.content
        assert r.helpful_count == 12

    def test_missing_content_skipped(self):
        data = [
            {"reviewIdx": 1, "reviewContents": ""},
            {"reviewIdx": 2, "reviewContents": "좋아요"},
        ]
        reviews = _parse_reviews_from_json(data)
        assert len(reviews) == 1
        assert reviews[0].content == "좋아요"

    def test_empty_returns_empty(self):
        assert _parse_reviews_from_json([]) == []
        assert _parse_reviews_from_json({}) == []


class TestParseReviewSummaryFromJson:
    def test_parses_summary(self, sample_review_json):
        summary = _parse_summary_from_json(sample_review_json, "16960793")
        assert summary is not None
        assert summary.total_count == 42
        assert summary.average_rating == pytest.approx(4.5)

    def test_none_on_non_dict(self):
        assert _parse_summary_from_json([], "123") is None
        assert _parse_summary_from_json("string", "123") is None

    def test_none_when_no_data(self):
        assert _parse_summary_from_json({}, "123") is None
