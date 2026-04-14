"""Review and rating tools for Danawa products.

Danawa provides two types of user feedback:

* **리뷰 (Reviews)** — full written reviews with title, content, and rating.
* **의견 (Opinions / Q&A)** — shorter community opinions and Q&A threads.

Both are loaded via AJAX after the product detail page is rendered.  We
capture the JSON responses through Playwright network interception.

Known AJAX endpoints (may change with site updates)
----------------------------------------------------
* Reviews:  ``https://prod.danawa.com/info/ajax/getProductReview.ajax.php``
* Opinions: ``https://prod.danawa.com/info/ajax/getProductOpinion.ajax.php``

The module falls back to HTML parsing if JSON is not captured.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from typing import Any

from loguru import logger

from danawa_mcp.browser import get_browser
from danawa_mcp.models import Review, ReviewListResult, ReviewSummary

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DETAIL_BASE = "https://prod.danawa.com/info/"
_REVIEW_AJAX = "https://prod.danawa.com/info/ajax/getProductReview.ajax.php"
_OPINION_AJAX = "https://prod.danawa.com/info/ajax/getProductOpinion.ajax.php"


def _detail_url(product_id: str) -> str:
    return f"{_DETAIL_BASE}?pcode={product_id}"


# ---------------------------------------------------------------------------
# JSON parsers
# ---------------------------------------------------------------------------


def _parse_reviews_from_json(data: Any) -> list[Review]:
    """Parse a Danawa review list JSON payload.

    Expected shape (simplified)::

        {
          "reviewList": [
            {
              "reviewIdx": 123456,
              "writerNick": "hong**",
              "writeDate": "2024-03-15",
              "starPoint": 5,
              "reviewTitle": "정말 좋아요",
              "reviewContents": "배터리도 오래 가고 ...",
              "goodCount": 12
            }
          ]
        }
    """
    reviews: list[Review] = []

    if isinstance(data, dict):
        for key in ("reviewList", "list", "data", "items", "commentList"):
            if isinstance(data.get(key), list):
                data = data[key]
                break

    if not isinstance(data, list):
        return reviews

    for item in data:
        if not isinstance(item, dict):
            continue

        content = str(
            item.get("reviewContents")
            or item.get("content")
            or item.get("comment")
            or item.get("opinionContents")
            or ""
        ).strip()
        if not content:
            continue

        raw_rating = item.get("starPoint") or item.get("star") or item.get("rating")
        rating: int | None = None
        if raw_rating is not None:
            with contextlib.suppress(ValueError, TypeError):
                rating = int(float(str(raw_rating)))

        reviews.append(
            Review(
                id=str(item.get("reviewIdx") or item.get("idx") or item.get("id") or ""),
                author=str(item.get("writerNick") or item.get("writer") or item.get("author") or "")
                or None,
                date=str(item.get("writeDate") or item.get("date") or "") or None,
                rating=rating,
                title=str(item.get("reviewTitle") or item.get("title") or "") or None,
                content=content,
                helpful_count=int(item.get("goodCount") or item.get("helpfulCount") or 0),
            )
        )

    return reviews


def _parse_summary_from_json(data: Any, product_id: str) -> ReviewSummary | None:
    """Parse review statistics from a JSON payload."""
    if not isinstance(data, dict):
        return None

    total = 0
    avg: float | None = None

    for tc_key in ("totalCount", "total", "count", "reviewCount"):
        v = data.get(tc_key)
        if v is not None:
            with contextlib.suppress(ValueError, TypeError):
                total = int(v)
                break

    for ar_key in ("averageStar", "avgStar", "averageRating", "avgRating"):
        v = data.get(ar_key)
        if v is not None:
            with contextlib.suppress(ValueError, TypeError):
                avg = float(v)
                break

    if total == 0 and avg is None:
        return None

    # Rating distribution (1-5)
    dist: dict[int, int] = {}
    for k in ("starDist", "ratingDist", "starDistribution"):
        rd = data.get(k)
        if isinstance(rd, dict):
            for star_str, cnt in rd.items():
                with contextlib.suppress(ValueError, TypeError):
                    dist[int(star_str)] = int(cnt)
            break

    return ReviewSummary(
        product_id=product_id,
        total_count=total,
        average_rating=avg,
        rating_distribution=dist,
    )


# ---------------------------------------------------------------------------
# HTML fallback parsers
# ---------------------------------------------------------------------------


def _parse_reviews_from_html(html: str) -> list[Review]:
    """Extract reviews from Danawa product detail page HTML (best-effort)."""
    reviews: list[Review] = []

    # Danawa review blocks look like:
    # <div class="review_list_wrap">
    #   <div class="revu_item"> ... </div>
    # </div>
    block_re = re.compile(
        r'<div[^>]+class="[^"]*revu_item[^"]*"[^>]*>(.*?)</div>\s*</div>',
        re.DOTALL,
    )
    author_re = re.compile(r'<span[^>]+class="[^"]*nick[^"]*"[^>]*>([^<]+)</span>')
    date_re = re.compile(r'<span[^>]+class="[^"]*date[^"]*"[^>]*>([^<]+)</span>')
    star_re = re.compile(r'<span[^>]+class="[^"]*star[^"]*"[^>]*>([^<]+)</span>')
    content_re = re.compile(
        r'<p[^>]+class="[^"]*review_cont[^"]*"[^>]*>(.*?)</p>',
        re.DOTALL,
    )

    for bm in block_re.finditer(html):
        block = bm.group(1)
        cm = content_re.search(block)
        if not cm:
            continue
        content = re.sub(r"<[^>]+>", "", cm.group(1)).strip()
        if not content:
            continue

        author_m = author_re.search(block)
        date_m = date_re.search(block)
        star_m = star_re.search(block)
        rating: int | None = None
        if star_m:
            with contextlib.suppress(ValueError):
                rating = int(float(star_m.group(1).strip()))

        reviews.append(
            Review(
                author=author_m.group(1).strip() if author_m else None,
                date=date_m.group(1).strip() if date_m else None,
                rating=rating,
                content=content,
            )
        )

    return reviews


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------


async def get_product_reviews(
    product_id: str,
    page: int = 1,
    per_page: int = 20,
) -> ReviewListResult:
    """제품 리뷰 목록을 가져옵니다.

    Parameters
    ----------
    product_id:
        다나와 제품 코드 (pcode).
    page:
        페이지 번호 (1부터 시작).
    per_page:
        페이지당 리뷰 수 (기본값: 20).

    Returns
    -------
    ReviewListResult
        리뷰 목록, 전체 개수, 평점 통계를 포함한 결과.

    Notes
    -----
    리뷰 데이터는 제품 상세 페이지에서 Playwright 네트워크 캡처를 통해
    수집하거나, AJAX 엔드포인트에 직접 요청하여 가져옵니다.
    """
    url = _detail_url(product_id)
    browser = await get_browser()
    logger.info("get_product_reviews: product_id={}, page={}", product_id, page)

    # Open the product page; this triggers AJAX calls for reviews
    page_obj, capture = await browser.navigate_and_interact(url)
    try:
        # Wait a moment for async review loading
        await asyncio.sleep(1.5)

        # Try direct AJAX call (reuses browser session / cookies)
        try:
            ajax_data = await browser.fetch_json(
                _REVIEW_AJAX,
                {"pcode": product_id, "page": page, "limit": per_page},
            )
        except Exception:
            ajax_data = None

        html = await page_obj.content()
        captured = capture.get()
    finally:
        await page_obj.close()

    reviews: list[Review] = []
    summary: ReviewSummary | None = None
    total = 0

    # Check direct AJAX response first
    if ajax_data:
        reviews = _parse_reviews_from_json(ajax_data)
        summary = _parse_summary_from_json(ajax_data, product_id)
        total = _parse_total_from_json(ajax_data)

    # Then check network capture
    if not reviews:
        for resp in captured:
            data = resp.get("data")
            r = _parse_reviews_from_json(data)
            if r:
                reviews = r
                if not summary:
                    summary = _parse_summary_from_json(data, product_id)
                if not total:
                    total = _parse_total_from_json(data)
                break

    # HTML fallback
    if not reviews:
        reviews = _parse_reviews_from_html(html)

    logger.debug("get_product_reviews({}) → {} reviews", product_id, len(reviews))

    return ReviewListResult(
        product_id=product_id,
        total_count=total or len(reviews),
        page=page,
        per_page=per_page,
        reviews=reviews[:per_page],
        summary=summary,
    )


async def get_product_opinions(
    product_id: str,
    page: int = 1,
    per_page: int = 20,
) -> ReviewListResult:
    """제품 커뮤니티 의견(Q&A) 목록을 가져옵니다.

    Parameters
    ----------
    product_id:
        다나와 제품 코드 (pcode).
    page:
        페이지 번호 (1부터 시작).
    per_page:
        페이지당 의견 수.

    Returns
    -------
    ReviewListResult
        커뮤니티 의견 목록.
    """
    browser = await get_browser()
    logger.info("get_product_opinions: product_id={}, page={}", product_id, page)

    try:
        ajax_data = await browser.fetch_json(
            _OPINION_AJAX,
            {"pcode": product_id, "page": page, "limit": per_page},
        )
    except Exception:
        ajax_data = None

    reviews: list[Review] = []
    total = 0

    if ajax_data:
        reviews = _parse_reviews_from_json(ajax_data)
        total = _parse_total_from_json(ajax_data)

    if not reviews:
        # Fall back to loading the full page and capturing
        url = _detail_url(product_id)
        html, captured = await browser.navigate(url)
        for resp in captured:
            r = _parse_reviews_from_json(resp.get("data"))
            if r:
                reviews = r
                break
        if not reviews:
            reviews = _parse_reviews_from_html(html)

    logger.debug("get_product_opinions({}) → {} opinions", product_id, len(reviews))

    return ReviewListResult(
        product_id=product_id,
        total_count=total or len(reviews),
        page=page,
        per_page=per_page,
        reviews=reviews[:per_page],
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_total_from_json(data: Any) -> int:
    if not isinstance(data, dict):
        return 0
    for key in ("totalCount", "total", "count", "reviewCount"):
        v = data.get(key)
        if v is not None:
            try:
                return int(v)
            except (ValueError, TypeError):
                pass
    return 0
