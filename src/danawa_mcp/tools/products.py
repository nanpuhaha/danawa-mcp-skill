"""Product listing, filtering, searching, and detail tools for Danawa.

Workflow
--------
1. **List/search products** — :func:`list_products` or :func:`search_products`
   return a :class:`~danawa_mcp.models.ProductListResult` including a list of
   :class:`~danawa_mcp.models.FilterGroup` objects that describe the available
   filter options for the current result set.

2. **Get filters** — :func:`get_product_filters` navigates to a category page
   and returns the available filter groups *before* any products are applied.

3. **Apply filters** — pass a ``filters`` dict of ``{filter_key: [value, ...]}``
   to :func:`list_products` to narrow down results.

4. **Product detail** — :func:`get_product_detail` navigates to the detail page
   and returns full specs, images, and pricing.

URL patterns used
-----------------
* Category list:   ``https://prod.danawa.com/list/?cate=<id>``
* Search:          ``https://search.danawa.com/dsearch.php?query=<q>``
* Product detail:  ``https://prod.danawa.com/info/?pcode=<id>``
"""

from __future__ import annotations

import contextlib
import re
from typing import Any
from urllib.parse import urlencode

from loguru import logger

from danawa_mcp.browser import get_browser
from danawa_mcp.models import (
    FilterGroup,
    FilterOption,
    ProductDetail,
    ProductListResult,
    ProductSpec,
    ProductSummary,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LIST_BASE = "https://prod.danawa.com/list/"
_SEARCH_BASE = "https://search.danawa.com/dsearch.php"
_DETAIL_BASE = "https://prod.danawa.com/info/"

# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------


def _list_url(category_id: str, filters: dict[str, list[str]] | None = None, page: int = 1) -> str:
    params: dict[str, Any] = {"cate": category_id, "page": page}
    if filters:
        for key, values in filters.items():
            params[key] = ",".join(values)
    return f"{_LIST_BASE}?{urlencode(params)}"


def _search_url(query: str, page: int = 1) -> str:
    return f"{_SEARCH_BASE}?{urlencode({'query': query, 'page': page})}"


def _detail_url(product_id: str) -> str:
    return f"{_DETAIL_BASE}?pcode={product_id}"


def _extract_pcode(url: str) -> str | None:
    m = re.search(r"[?&]pcode=(\d+)", url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# JSON parsers — prefer captured network responses
# ---------------------------------------------------------------------------


def _json_to_products(data: Any) -> list[ProductSummary]:
    """Parse a Danawa product list JSON payload into ProductSummary objects.

    Danawa's internal API typically returns a structure like::

        {
          "productDetailList": [
            {
              "productCode": "16960793",
              "productName": "삼성전자 갤럭시북4 Pro ...",
              "lowPrice": 1990000,
              "image": "//img.danawa.com/prod_img/...",
              "shopCount": 12,
              "reviewCount": 42,
              "star": "4.5",
              ...
            }
          ]
        }

    This helper handles several known variants.
    """
    products: list[ProductSummary] = []

    if isinstance(data, dict):
        # Try common wrapper keys
        for key in ("productDetailList", "productList", "list", "data", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if not isinstance(data, list):
        return products

    for item in data:
        if not isinstance(item, dict):
            continue

        pid = str(
            item.get("productCode") or item.get("pcode") or item.get("code") or item.get("id") or ""
        )
        name = str(item.get("productName") or item.get("name") or "")
        if not pid or not name:
            continue

        raw_price = item.get("lowPrice") or item.get("price") or item.get("minPrice")
        price: int | None = None
        if raw_price is not None:
            with contextlib.suppress(ValueError):
                price = int(str(raw_price).replace(",", ""))

        image = str(item.get("image") or item.get("imageUrl") or "")
        if image.startswith("//"):
            image = "https:" + image

        raw_rating = item.get("star") or item.get("rating")
        rating: float | None = None
        if raw_rating is not None:
            with contextlib.suppress(ValueError, TypeError):
                rating = float(raw_rating)

        products.append(
            ProductSummary(
                id=pid,
                name=name,
                price=price,
                image_url=image or None,
                shop_count=int(item.get("shopCount") or item.get("sellerCount") or 0),
                rating=rating,
                review_count=int(item.get("reviewCount") or item.get("commentCount") or 0),
                url=_detail_url(pid),
            )
        )

    return products


def _json_to_filters(data: Any) -> list[FilterGroup]:
    """Parse filter/option data from a captured JSON response.

    Known schema variants::

        {"filterList": [{"filterName": "CPU", "filterCode": "cpu",
                         "optionList": [{"optionName": "i7", "count": 124}]}]}
    """
    groups: list[FilterGroup] = []

    if isinstance(data, dict):
        for key in ("filterList", "filters", "optionGroups"):
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if not isinstance(data, list):
        return groups

    for item in data:
        if not isinstance(item, dict):
            continue

        group_key = str(item.get("filterCode") or item.get("code") or item.get("key") or "")
        group_name = str(item.get("filterName") or item.get("name") or "")
        if not group_key or not group_name:
            continue

        options: list[FilterOption] = []
        raw_opts = item.get("optionList") or item.get("options") or []
        for opt in raw_opts:
            if not isinstance(opt, dict):
                continue
            label = str(opt.get("optionName") or opt.get("name") or opt.get("label") or "")
            value = str(opt.get("optionCode") or opt.get("value") or opt.get("code") or label)
            count = int(opt.get("count") or opt.get("productCount") or 0)
            if label:
                options.append(FilterOption(value=value, label=label, count=count))

        groups.append(FilterGroup(key=group_key, name=group_name, options=options))

    return groups


def _json_to_total(data: Any) -> int:
    """Extract total product count from JSON payload."""
    if isinstance(data, dict):
        for key in ("totalCount", "total", "count", "totalProductCount"):
            v = data.get(key)
            if v is not None:
                try:
                    return int(v)
                except (ValueError, TypeError):
                    pass
    return 0


# ---------------------------------------------------------------------------
# HTML-based parsers (fallback)
# ---------------------------------------------------------------------------


def _html_to_products(html: str) -> list[ProductSummary]:
    """Extract basic product summaries from Danawa product list HTML.

    This is a best-effort fallback for when JSON capture is unavailable.
    Selectors are based on Danawa's current markup as of 2024.
    """
    products: list[ProductSummary] = []

    # Each product card has an id like "productItem_<pcode>"
    block_re = re.compile(
        r'id="productItem_(\d+)".*?<p[^>]+class="[^"]*prod-name[^"]*"[^>]*>'
        r"\s*<a[^>]*>([^<]+)</a>",
        re.DOTALL,
    )
    price_re = re.compile(r'<p[^>]+class="[^"]*price[^"]*"[^>]*>.*?(\d[\d,]+)\s*원', re.DOTALL)
    img_re = re.compile(r'<img[^>]+src="(//[^"]+)"[^>]*/>', re.DOTALL)

    for m in block_re.finditer(html):
        pid = m.group(1)
        name = re.sub(r"\s+", " ", m.group(2)).strip()
        block = m.group(0)

        pm = price_re.search(block)
        price: int | None = None
        if pm:
            with contextlib.suppress(ValueError):
                price = int(pm.group(1).replace(",", ""))

        im = img_re.search(block)
        image = ("https:" + im.group(1)) if im else None

        products.append(
            ProductSummary(
                id=pid,
                name=name,
                price=price,
                image_url=image,
                url=_detail_url(pid),
            )
        )

    return products


def _html_to_filters(html: str) -> list[FilterGroup]:
    """Extract filter groups from Danawa category list page HTML.

    The filter sidebar uses a structure like::

        <div class="spec-filter">
          <div class="spec-item">
            <strong class="tit-filter">CPU</strong>
            <ul class="list-spec">
              <li><label><input type="checkbox" name="spec" value="i7"> i7 (124)</label></li>
            </ul>
          </div>
        </div>
    """
    groups: list[FilterGroup] = []

    group_re = re.compile(
        r'<div[^>]+class="[^"]*spec-item[^"]*"[^>]*>(.*?)</div>\s*</div>',
        re.DOTALL,
    )
    title_re = re.compile(r'<strong[^>]*class="[^"]*tit-filter[^"]*"[^>]*>([^<]+)</strong>')
    opt_re = re.compile(
        r'<input[^>]+type="checkbox"[^>]+name="([^"]+)"[^>]+value="([^"]+)"[^>]*>([^<(]+)'
        r"(?:\((\d+)\))?",
        re.DOTALL,
    )

    for gm in group_re.finditer(html):
        block = gm.group(1)
        tm = title_re.search(block)
        if not tm:
            continue
        group_name = tm.group(1).strip()
        options: list[FilterOption] = []
        seen_vals: set[str] = set()
        for om in opt_re.finditer(block):
            _key, value, label, count_str = om.group(1), om.group(2), om.group(3), om.group(4)
            label = label.strip()
            if not label or value in seen_vals:
                continue
            seen_vals.add(value)
            count = int(count_str) if count_str else 0
            options.append(FilterOption(value=value, label=label, count=count))

        if options:
            groups.append(FilterGroup(key=group_name.lower(), name=group_name, options=options))

    return groups


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------


async def get_product_filters(category_id: str) -> list[FilterGroup]:
    """카테고리의 필터 옵션 목록을 가져옵니다.

    Parameters
    ----------
    category_id:
        카테고리 ID (e.g. ``"10228"``).

    Returns
    -------
    list[FilterGroup]
        해당 카테고리에서 사용 가능한 필터 그룹 목록.
        각 그룹에는 선택 가능한 옵션과 제품 수가 포함됩니다.
    """
    url = _list_url(category_id)
    browser = await get_browser()
    logger.info("get_product_filters: category_id={}", category_id)

    html, captured = await browser.navigate(url)

    # Prefer JSON
    for resp in captured:
        groups = _json_to_filters(resp.get("data"))
        if groups:
            logger.debug("Parsed {} filter groups from JSON", len(groups))
            return groups

    # Fallback: HTML
    groups = _html_to_filters(html)
    logger.debug("Parsed {} filter groups from HTML", len(groups))
    return groups


async def list_products(
    category_id: str,
    filters: dict[str, list[str]] | None = None,
    page: int = 1,
    per_page: int = 20,
) -> ProductListResult:
    """카테고리에서 제품 목록을 가져옵니다 (필터 적용 가능).

    Parameters
    ----------
    category_id:
        카테고리 ID.
    filters:
        적용할 필터 딕셔너리. 키는 필터 코드, 값은 선택된 옵션 값 리스트.
        예: ``{"cpu": ["i7", "i9"], "memory": ["16GB"]}``
    page:
        페이지 번호 (1부터 시작).
    per_page:
        페이지당 제품 수 (기본값: 20).

    Returns
    -------
    ProductListResult
        제품 목록, 전체 개수, 사용 가능한 필터 그룹을 포함한 결과.
    """
    url = _list_url(category_id, filters, page)
    browser = await get_browser()
    logger.info("list_products: category_id={}, filters={}, page={}", category_id, filters, page)

    html, captured = await browser.navigate(url)

    products: list[ProductSummary] = []
    filter_groups: list[FilterGroup] = []
    total = 0

    for resp in captured:
        data = resp.get("data")
        if not products:
            p = _json_to_products(data)
            if p:
                products = p
        if not filter_groups:
            fg = _json_to_filters(data)
            if fg:
                filter_groups = fg
        if not total:
            total = _json_to_total(data)

    if not products:
        products = _html_to_products(html)
    if not filter_groups:
        filter_groups = _html_to_filters(html)

    logger.debug("list_products → {} products, {} filter groups", len(products), len(filter_groups))

    return ProductListResult(
        category_id=category_id,
        total_count=total or len(products),
        page=page,
        per_page=per_page,
        products=products[:per_page],
        filter_groups=filter_groups,
    )


async def search_products(
    query: str,
    page: int = 1,
    per_page: int = 20,
) -> ProductListResult:
    """키워드로 제품을 검색합니다.

    Parameters
    ----------
    query:
        검색할 키워드 (e.g. ``"RTX 4090 그래픽카드"``).
    page:
        페이지 번호.
    per_page:
        페이지당 제품 수.

    Returns
    -------
    ProductListResult
        검색 결과 제품 목록.
    """
    url = _search_url(query, page)
    browser = await get_browser()
    logger.info("search_products: query='{}', page={}", query, page)

    html, captured = await browser.navigate(url)

    products: list[ProductSummary] = []
    total = 0

    for resp in captured:
        data = resp.get("data")
        if not products:
            p = _json_to_products(data)
            if p:
                products = p
        if not total:
            total = _json_to_total(data)

    if not products:
        products = _html_to_products(html)

    logger.debug("search_products('{}') → {} results", query, len(products))

    return ProductListResult(
        query=query,
        total_count=total or len(products),
        page=page,
        per_page=per_page,
        products=products[:per_page],
    )


# ---------------------------------------------------------------------------
# Product detail helpers
# ---------------------------------------------------------------------------


def _json_to_detail(data: Any, product_id: str) -> ProductDetail | None:
    """Parse a product detail JSON response."""
    if not isinstance(data, dict):
        return None

    for wrapper in ("productDetail", "product", "data"):
        if isinstance(data.get(wrapper), dict):
            data = data[wrapper]
            break

    name = str(data.get("productName") or data.get("name") or "")
    if not name:
        return None

    specs: list[ProductSpec] = []
    raw_specs = data.get("specList") or data.get("specs") or []
    if isinstance(raw_specs, list):
        for s in raw_specs:
            if isinstance(s, dict):
                k = str(s.get("specName") or s.get("name") or "")
                v = str(s.get("specValue") or s.get("value") or "")
                if k and v:
                    specs.append(ProductSpec(name=k, value=v))
    elif isinstance(raw_specs, dict):
        for k, v in raw_specs.items():
            specs.append(ProductSpec(name=str(k), value=str(v)))

    image_urls: list[str] = []
    for img_key in ("imageList", "images", "imgList"):
        if isinstance(data.get(img_key), list):
            for img in data[img_key]:
                url = str(img.get("imageUrl") or img.get("url") or img or "")
                if url:
                    if url.startswith("//"):
                        url = "https:" + url
                    image_urls.append(url)
            break

    raw_price = data.get("lowPrice") or data.get("price") or data.get("minPrice")
    price: int | None = None
    if raw_price is not None:
        with contextlib.suppress(ValueError):
            price = int(str(raw_price).replace(",", ""))

    return ProductDetail(
        id=product_id,
        name=name,
        brand=str(data.get("brandName") or data.get("brand") or "") or None,
        category=str(data.get("categoryName") or data.get("category") or "") or None,
        price=price,
        specs=specs,
        image_urls=image_urls,
        url=_detail_url(product_id),
    )


def _html_to_detail(html: str, product_id: str) -> ProductDetail:
    """Extract product detail from HTML (fallback)."""
    # Product name
    name_m = re.search(
        r'<h3[^>]+class="[^"]*prod-buy-header__title[^"]*"[^>]*>([^<]+)</h3>'
        r'|<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
        html,
    )
    name = ""
    if name_m:
        name = (name_m.group(1) or name_m.group(2) or "").strip()

    # Price
    price_m = re.search(r'"lowPrice"\s*:\s*"?(\d+)"?', html)
    price: int | None = None
    if price_m:
        with contextlib.suppress(ValueError):
            price = int(price_m.group(1))

    # Spec table  — Danawa renders a <table class="spec_tbl"> with th/td pairs
    specs: list[ProductSpec] = []
    spec_re = re.compile(r"<th[^>]*>([^<]+)</th>\s*<td[^>]*>([^<]+)</td>", re.DOTALL)
    for sm in spec_re.finditer(html):
        k = re.sub(r"\s+", " ", sm.group(1)).strip()
        v = re.sub(r"\s+", " ", sm.group(2)).strip()
        if k and v:
            specs.append(ProductSpec(name=k, value=v))

    # Images
    img_re = re.compile(r'<img[^>]+src="(https?://[^"]+(?:\.jpg|\.png|\.webp))"', re.IGNORECASE)
    image_urls = list(dict.fromkeys(img_re.findall(html)))[:10]

    return ProductDetail(
        id=product_id,
        name=name or f"Product {product_id}",
        price=price,
        specs=specs,
        image_urls=image_urls,
        url=_detail_url(product_id),
    )


async def get_product_detail(product_id: str) -> ProductDetail:
    """제품 상세 정보를 가져옵니다.

    Parameters
    ----------
    product_id:
        다나와 제품 코드 (pcode). 제품 목록에서 ``id`` 필드로 얻을 수 있습니다.

    Returns
    -------
    ProductDetail
        제품 사양, 이미지 URL, 가격 등을 포함한 상세 정보.
    """
    url = _detail_url(product_id)
    browser = await get_browser()
    logger.info("get_product_detail: product_id={}", product_id)

    html, captured = await browser.navigate(url)

    # Prefer JSON
    for resp in captured:
        detail = _json_to_detail(resp.get("data"), product_id)
        if detail:
            logger.debug("Parsed product detail from JSON for {}", product_id)
            return detail

    # Fallback: HTML
    detail = _html_to_detail(html, product_id)
    logger.debug("Parsed product detail from HTML for {}", product_id)
    return detail
