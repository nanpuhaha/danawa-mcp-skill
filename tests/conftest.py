"""Shared pytest fixtures for danawa_mcp tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_product_json() -> dict:
    """Minimal Danawa-like product list JSON payload."""
    return {
        "totalCount": 2,
        "productDetailList": [
            {
                "productCode": "16960793",
                "productName": "삼성전자 갤럭시북4 Pro 16 NT960XGK-KC72S",
                "lowPrice": "1990000",
                "image": "//img.danawa.com/prod_img/500000/123/456/img/16960793_1.jpg",
                "shopCount": 12,
                "reviewCount": 42,
                "star": "4.5",
            },
            {
                "productCode": "17000001",
                "productName": "LG전자 그램 16 16Z90S-GD79K",
                "lowPrice": "2150000",
                "image": "//img.danawa.com/prod_img/500000/001/001/img/17000001_1.jpg",
                "shopCount": 8,
                "reviewCount": 19,
                "star": "4.7",
            },
        ],
    }


@pytest.fixture
def sample_filter_json() -> dict:
    """Minimal Danawa-like filter group JSON payload."""
    return {
        "filterList": [
            {
                "filterCode": "brand",
                "filterName": "브랜드",
                "optionList": [
                    {"optionCode": "samsung", "optionName": "삼성전자", "count": 45},
                    {"optionCode": "lg", "optionName": "LG전자", "count": 38},
                    {"optionCode": "apple", "optionName": "애플", "count": 22},
                ],
            },
            {
                "filterCode": "cpu",
                "filterName": "CPU",
                "optionList": [
                    {"optionCode": "i7", "optionName": "인텔 i7", "count": 60},
                    {"optionCode": "i9", "optionName": "인텔 i9", "count": 20},
                    {"optionCode": "m3", "optionName": "Apple M3", "count": 22},
                ],
            },
        ]
    }


@pytest.fixture
def sample_review_json() -> dict:
    """Minimal Danawa-like review list JSON payload."""
    return {
        "totalCount": 42,
        "averageStar": 4.5,
        "reviewList": [
            {
                "reviewIdx": 1001,
                "writerNick": "hong**",
                "writeDate": "2024-03-15",
                "starPoint": 5,
                "reviewTitle": "정말 좋아요",
                "reviewContents": "배터리도 오래 가고 화면도 선명합니다.",
                "goodCount": 12,
            },
            {
                "reviewIdx": 1002,
                "writerNick": "kim**",
                "writeDate": "2024-02-10",
                "starPoint": 4,
                "reviewTitle": "전반적으로 만족",
                "reviewContents": "가격 대비 성능이 좋습니다.",
                "goodCount": 5,
            },
        ],
    }


@pytest.fixture
def sample_category_json() -> list:
    """Minimal Danawa-like category JSON payload."""
    return [
        {"cateCd": "10225", "cateName": "노트북", "parentCateCd": None},
        {"cateCd": "10228", "cateName": "데스크탑", "parentCateCd": None},
        {"cateCd": "10231", "cateName": "그래픽카드", "parentCateCd": "10228"},
    ]
