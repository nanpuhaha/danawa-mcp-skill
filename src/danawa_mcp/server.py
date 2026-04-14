"""FastMCP server for Danawa — registers all tools and manages browser lifecycle.

Run as a standalone MCP server (stdio transport, default)::

    danawa-mcp
    # or
    python -m danawa_mcp.server

Run with HTTP transport::

    danawa-mcp --transport streamable-http --port 8000

Architecture
------------
The server uses a :func:`lifespan` context manager to start and stop the
shared :class:`~danawa_mcp.browser.DanawaBrowser` singleton.  All tool
functions call :func:`~danawa_mcp.browser.get_browser` to obtain the shared
instance — the browser is never created per-request to avoid expensive
startup overhead.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastmcp import FastMCP
from loguru import logger
from pydantic import Field

from danawa_mcp import __version__
from danawa_mcp.browser import close_browser, get_browser
from danawa_mcp.models import Category as CategoryModel
from danawa_mcp.models import (
    FilterGroup,
    ProductDetail,
    ProductListResult,
    ReviewListResult,
)
from danawa_mcp.tools.categories import (
    get_subcategories,
    list_main_categories,
    search_categories,
)
from danawa_mcp.tools.products import (
    get_product_detail,
    get_product_filters,
    list_products,
    search_products,
)
from danawa_mcp.tools.reviews import get_product_opinions, get_product_reviews

# ---------------------------------------------------------------------------
# Lifespan — warm up the browser before the first request
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Start the shared browser on server startup; stop it on shutdown."""
    logger.info("Danawa MCP server starting (v{})", __version__)
    await get_browser()  # pre-warm
    yield
    await close_browser()
    logger.info("Danawa MCP server stopped")


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="Danawa MCP",
    instructions=(
        "다나와(danawa.com) 제품 검색 및 비교 도구입니다.\n"
        "카테고리 탐색 → 필터 조회 → 제품 목록 → 제품 상세 → 리뷰 순서로 활용하세요.\n\n"
        "권장 워크플로우:\n"
        "1. list_main_categories 또는 search_categories 로 카테고리 ID 확인\n"
        "2. get_product_filters 로 사용 가능한 필터 옵션 확인\n"
        "3. list_products 에 필터를 적용해 제품 수 줄이기\n"
        "4. get_product_detail 로 관심 제품의 상세 사양 확인\n"
        "5. get_product_reviews / get_product_opinions 로 사용자 의견 확인"
    ),
    version=__version__,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Category tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def danawa_list_main_categories() -> list[CategoryModel]:
    """다나와의 메인 카테고리 목록을 반환합니다.

    결과에는 각 카테고리의 ID, 이름, URL 이 포함됩니다.
    ID 는 이후 필터 조회나 제품 목록 조회에 사용하세요.
    """
    return await list_main_categories()


@mcp.tool()
async def danawa_get_subcategories(
    category_id: Annotated[str, Field(description="상위 카테고리 ID (숫자 문자열)")],
) -> list[CategoryModel]:
    """특정 카테고리의 하위 카테고리 목록을 반환합니다.

    Parameters
    ----------
    category_id:
        상위 카테고리 ID.  `danawa_list_main_categories` 결과의 `id` 필드 값.
    """
    return await get_subcategories(category_id)


@mcp.tool()
async def danawa_search_categories(
    keyword: Annotated[
        str, Field(description="검색할 카테고리 키워드 (예: '노트북', '그래픽카드')")
    ],
) -> list[CategoryModel]:
    """카테고리 이름으로 검색합니다.

    Parameters
    ----------
    keyword:
        카테고리 이름에 포함될 키워드.
    """
    return await search_categories(keyword)


# ---------------------------------------------------------------------------
# Filter & product list tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def danawa_get_product_filters(
    category_id: Annotated[str, Field(description="카테고리 ID")],
) -> list[FilterGroup]:
    """카테고리에서 사용 가능한 필터 옵션 목록을 반환합니다.

    반환된 `FilterGroup` 목록에는 브랜드, 가격 범위, 제품 사양 등
    체크박스로 선택 가능한 옵션들이 포함됩니다.

    Parameters
    ----------
    category_id:
        필터 목록을 조회할 카테고리 ID.
    """
    return await get_product_filters(category_id)


@mcp.tool()
async def danawa_list_products(
    category_id: Annotated[str, Field(description="카테고리 ID")],
    filters: Annotated[
        dict[str, list[str]] | None,
        Field(
            default=None,
            description=(
                "적용할 필터. 키는 필터 코드, 값은 선택할 옵션 값 목록. "
                '예: {"brand": ["삼성", "LG"], "memory": ["16GB"]}'
            ),
        ),
    ] = None,
    page: Annotated[int, Field(default=1, ge=1, description="페이지 번호 (1부터)")] = 1,
    per_page: Annotated[int, Field(default=20, ge=1, le=100, description="페이지당 제품 수")] = 20,
) -> ProductListResult:
    """카테고리 제품 목록을 가져옵니다 (필터 적용 가능).

    Parameters
    ----------
    category_id:
        카테고리 ID.
    filters:
        적용할 필터 딕셔너리 (`danawa_get_product_filters` 결과 기반).
    page:
        페이지 번호.
    per_page:
        페이지당 제품 수 (최대 100).
    """
    return await list_products(category_id, filters, page, per_page)


@mcp.tool()
async def danawa_search_products(
    query: Annotated[str, Field(description="검색 키워드 (예: 'RTX 4090 그래픽카드')")],
    page: Annotated[int, Field(default=1, ge=1, description="페이지 번호")] = 1,
    per_page: Annotated[int, Field(default=20, ge=1, le=100, description="페이지당 결과 수")] = 20,
) -> ProductListResult:
    """키워드로 다나와 전체 제품을 검색합니다.

    Parameters
    ----------
    query:
        검색 키워드.
    page:
        결과 페이지 번호.
    per_page:
        페이지당 결과 수 (최대 100).
    """
    return await search_products(query, page, per_page)


# ---------------------------------------------------------------------------
# Product detail tool
# ---------------------------------------------------------------------------


@mcp.tool()
async def danawa_get_product_detail(
    product_id: Annotated[
        str, Field(description="다나와 제품 코드 (pcode). 제품 목록의 `id` 필드 값.")
    ],
) -> ProductDetail:
    """제품의 상세 정보를 가져옵니다.

    반환값에는 사양(스펙) 목록, 이미지 URL, 가격 정보가 포함됩니다.

    Parameters
    ----------
    product_id:
        다나와 제품 코드. `danawa_list_products` 또는 `danawa_search_products`
        결과의 `id` 필드 값.
    """
    return await get_product_detail(product_id)


# ---------------------------------------------------------------------------
# Review tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def danawa_get_product_reviews(
    product_id: Annotated[str, Field(description="다나와 제품 코드 (pcode)")],
    page: Annotated[int, Field(default=1, ge=1, description="페이지 번호")] = 1,
    per_page: Annotated[int, Field(default=20, ge=1, le=100, description="페이지당 리뷰 수")] = 20,
) -> ReviewListResult:
    """제품의 사용자 리뷰 목록을 가져옵니다.

    각 리뷰에는 별점, 제목, 본문, 작성일, 도움이 됐어요 수가 포함됩니다.

    Parameters
    ----------
    product_id:
        다나와 제품 코드.
    page:
        페이지 번호.
    per_page:
        페이지당 리뷰 수 (최대 100).
    """
    return await get_product_reviews(product_id, page, per_page)


@mcp.tool()
async def danawa_get_product_opinions(
    product_id: Annotated[str, Field(description="다나와 제품 코드 (pcode)")],
    page: Annotated[int, Field(default=1, ge=1, description="페이지 번호")] = 1,
    per_page: Annotated[int, Field(default=20, ge=1, le=100, description="페이지당 의견 수")] = 20,
) -> ReviewListResult:
    """제품의 커뮤니티 의견(Q&A) 목록을 가져옵니다.

    Parameters
    ----------
    product_id:
        다나와 제품 코드.
    page:
        페이지 번호.
    per_page:
        페이지당 의견 수 (최대 100).
    """
    return await get_product_opinions(product_id, page, per_page)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point — ``danawa-mcp`` command."""
    mcp.run()


if __name__ == "__main__":
    main()
