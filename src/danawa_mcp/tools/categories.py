"""Category browsing tools for Danawa.

Danawa organises products into a three-level category hierarchy::

    메인 카테고리 (main)
      └── 중간 카테고리 (mid)
            └── 소분류 카테고리 (leaf)

Each category has a numeric *category ID* used in the URL::

    https://prod.danawa.com/list/?cate=<category_id>

Implementation notes
--------------------
* The full category tree is fetched from Danawa's main page navigation once
  and cached in-process for the lifetime of the MCP server.
* If Playwright network capture provides a JSON payload with the category
  tree (common in modern SPAs), we prefer that; otherwise we fall back to
  CSS-selector-based HTML parsing.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from danawa_mcp.browser import DANAWA_BASE_URL, get_browser
from danawa_mcp.models import Category

# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------

_category_cache: list[Category] | None = None

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_CATE_RE = re.compile(r"[?&]cate=(\d+)")


def _category_url(category_id: str) -> str:
    return f"https://prod.danawa.com/list/?cate={category_id}"


def _extract_cate_id(url: str) -> str | None:
    m = _CATE_RE.search(url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# HTML-based parsing helpers (fallback)
# ---------------------------------------------------------------------------


def _parse_categories_from_json(data: Any) -> list[Category]:
    """Try to extract categories from a captured JSON payload.

    Danawa sometimes exposes category data as a JSON array like::

        [{"cateCd": "10228", "cateName": "노트북", "parentCateCd": "10218", ...}]

    This helper handles that schema gracefully and returns an empty list if
    the shape does not match.
    """
    categories: list[Category] = []

    if not isinstance(data, list):
        return categories

    for item in data:
        if not isinstance(item, dict):
            continue
        cate_id = str(item.get("cateCd") or item.get("cateCode") or item.get("id") or "")
        cate_name = str(item.get("cateName") or item.get("name") or "")
        parent_id = (
            str(
                item.get("parentCateCd") or item.get("parentCateCode") or item.get("parentId") or ""
            )
            or None
        )
        if cate_id and cate_name:
            categories.append(
                Category(
                    id=cate_id,
                    name=cate_name,
                    parent_id=parent_id,
                    url=_category_url(cate_id),
                )
            )

    return categories


def _parse_categories_from_html(html: str) -> list[Category]:
    """Extract categories from the navigation HTML using regex.

    We look for anchor tags whose ``href`` contains ``cate=<digits>`` in the
    Danawa category navigation area.  This is intentionally lenient so it
    continues to work even if the surrounding markup changes slightly.
    """
    # Match links that contain a cate= parameter
    pattern = re.compile(
        r'<a[^>]+href="([^"]*[?&]cate=(\d+)[^"]*)"[^>]*>\s*([^<]+?)\s*</a>',
        re.IGNORECASE,
    )
    seen: set[str] = set()
    categories: list[Category] = []

    for match in pattern.finditer(html):
        href, cate_id, raw_name = match.group(1), match.group(2), match.group(3)
        name = re.sub(r"\s+", " ", raw_name).strip()
        if not name or cate_id in seen:
            continue
        seen.add(cate_id)
        # Skip very generic or empty names that are likely navigation chrome
        if len(name) < 2 or name in ("더보기", "전체"):
            continue
        categories.append(Category(id=cate_id, name=name, url=href))

    return categories


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------


async def list_main_categories() -> list[Category]:
    """카테고리 목록을 가져옵니다.

    Returns
    -------
    list[Category]
        다나와 메인 페이지에서 수집한 카테고리 목록.
        각 항목에는 ``id``, ``name``, ``url`` 이 포함됩니다.

    Notes
    -----
    결과는 프로세스 내에 캐싱됩니다. 서버 재시작 없이 최신 목록을
    강제로 다시 가져오려면 ``refresh_category_cache()`` 를 호출하세요.
    """
    global _category_cache
    if _category_cache is not None:
        logger.debug("Returning cached category list ({} items)", len(_category_cache))
        return _category_cache

    browser = await get_browser()
    logger.info("Fetching main categories from {}", DANAWA_BASE_URL)

    html, captured = await browser.navigate(DANAWA_BASE_URL)

    # Prefer JSON payload from network if available
    categories: list[Category] = []
    for resp in captured:
        cats = _parse_categories_from_json(resp.get("data"))
        if cats:
            categories = cats
            logger.debug("Parsed {} categories from JSON network response", len(cats))
            break

    # Fallback: parse HTML
    if not categories:
        categories = _parse_categories_from_html(html)
        logger.debug("Parsed {} categories from HTML", len(categories))

    _category_cache = categories
    return categories


async def get_subcategories(category_id: str) -> list[Category]:
    """특정 카테고리의 하위 카테고리 목록을 가져옵니다.

    Parameters
    ----------
    category_id:
        상위 카테고리 ID (숫자 문자열, e.g. ``"10228"``).

    Returns
    -------
    list[Category]
        해당 카테고리 페이지에서 발견된 하위 카테고리 목록.
    """
    url = _category_url(category_id)
    browser = await get_browser()
    logger.info("Fetching subcategories for category_id={}", category_id)

    html, captured = await browser.navigate(url)

    # Try JSON first
    categories: list[Category] = []
    for resp in captured:
        cats = _parse_categories_from_json(resp.get("data"))
        if cats:
            categories = [c for c in cats if c.parent_id == category_id or not c.parent_id]
            if categories:
                break

    # Fallback: HTML
    if not categories:
        all_cats = _parse_categories_from_html(html)
        categories = [c for c in all_cats if c.id != category_id]

    # Annotate parent
    for cat in categories:
        if cat.parent_id is None:
            cat.parent_id = category_id

    logger.debug("Found {} subcategories for {}", len(categories), category_id)
    return categories


async def search_categories(keyword: str) -> list[Category]:
    """카테고리 이름으로 검색합니다.

    Parameters
    ----------
    keyword:
        카테고리 이름에서 검색할 키워드 (대소문자 무시).

    Returns
    -------
    list[Category]
        키워드를 포함하는 카테고리 목록.
    """
    all_cats = await list_main_categories()
    kw = keyword.lower()
    results = [c for c in all_cats if kw in c.name.lower()]
    logger.debug("search_categories('{}') → {} results", keyword, len(results))
    return results


async def refresh_category_cache() -> list[Category]:
    """캐시를 무효화하고 카테고리 목록을 새로 가져옵니다."""
    global _category_cache
    _category_cache = None
    return await list_main_categories()
