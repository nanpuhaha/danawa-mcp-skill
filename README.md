# danawa-mcp-skill

다나와(danawa.com) 제품 검색 및 비교를 위한 **FastMCP** + **Playwright** 기반 MCP Skill.

AI 에이전트가 카테고리 탐색 → 필터 적용 → 제품 목록 확인 → 상세 정보 조회 → 리뷰 확인 워크플로우를 자동화할 수 있도록 설계되었습니다.

## 특징

- **카테고리 탐색** — 메인/하위 카테고리 트리를 탐색하고 원하는 제품군을 찾습니다.
- **필터 조회 및 적용** — 브랜드, 가격, 사양 등 다나와 필터 옵션을 조회하고 체크하여 제품 수를 줄입니다.
- **제품 목록** — 카테고리 또는 키워드 검색으로 페이지네이션된 제품 목록을 가져옵니다.
- **제품 상세** — 스펙 테이블, 이미지 URL, 가격 정보를 수집합니다.
- **리뷰 & 의견** — 사용자 리뷰와 커뮤니티 의견(Q&A)을 가져옵니다.
- **JSON 네트워크 캡처** — Playwright가 페이지를 탐색하는 동안 Danawa의 내부 AJAX JSON 응답을 실시간으로 캡처하여 HTML 파싱보다 정확하고 구조화된 데이터를 제공합니다.
- **사람처럼 행동** — 봇 탐지를 회피하기 위해 무작위 딜레이와 실제 브라우저 헤더를 사용합니다.

## 기술 스택

| 라이브러리 | 역할 |
|---|---|
| [FastMCP](https://github.com/jlowin/fastmcp) | MCP 서버 프레임워크 |
| [Playwright](https://playwright.dev/python/) | 헤드리스 브라우저 자동화 |
| [Pydantic v2](https://docs.pydantic.dev/) | 데이터 모델 및 유효성 검사 |
| [Loguru](https://loguru.readthedocs.io/) | 구조화된 로깅 |
| [Tenacity](https://tenacity.readthedocs.io/) | 재시도 로직 |
| [uv](https://docs.astral.sh/uv/) | 패키지 및 의존성 관리 |
| [Ruff](https://docs.astral.sh/ruff/) | 린터 + 포매터 |

## 설치

### 사전 요구사항

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (`pip install uv` 또는 공식 설치 방법)

### 의존성 설치

```bash
uv sync
python -m playwright install chromium
```

## 실행

### stdio transport (기본, Claude Desktop 등)

```bash
uv run danawa-mcp
```

### HTTP transport

```bash
uv run danawa-mcp --transport streamable-http --port 8000
```

## MCP 도구 목록

| 도구 | 설명 |
|---|---|
| `danawa_list_main_categories` | 메인 카테고리 목록 조회 |
| `danawa_get_subcategories` | 하위 카테고리 목록 조회 |
| `danawa_search_categories` | 카테고리 이름 검색 |
| `danawa_get_product_filters` | 카테고리별 필터 옵션 조회 |
| `danawa_list_products` | 카테고리 제품 목록 (필터 적용 가능) |
| `danawa_search_products` | 키워드 검색 |
| `danawa_get_product_detail` | 제품 상세 정보 (스펙, 이미지) |
| `danawa_get_product_reviews` | 제품 리뷰 목록 |
| `danawa_get_product_opinions` | 제품 커뮤니티 의견(Q&A) |

## Claude Desktop 설정 예시

`claude_desktop_config.json`에 아래 내용을 추가하세요:

```json
{
  "mcpServers": {
    "danawa": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/danawa-mcp-skill", "danawa-mcp"]
    }
  }
}
```

## 워크플로우 예시

```
1. danawa_list_main_categories()
   → [{"id": "10225", "name": "노트북"}, ...]

2. danawa_get_product_filters(category_id="10225")
   → [FilterGroup(key="brand", options=[...]), FilterGroup(key="cpu", options=[...])]

3. danawa_list_products(
       category_id="10225",
       filters={"brand": ["삼성전자"], "cpu": ["i7"]},
       page=1
   )
   → ProductListResult(total_count=45, products=[...])

4. danawa_get_product_detail(product_id="16960793")
   → ProductDetail(name="...", specs=[...], image_urls=[...])

5. danawa_get_product_reviews(product_id="16960793", page=1)
   → ReviewListResult(total_count=42, reviews=[...])
```

## 개발

```bash
# 개발 의존성 설치
uv sync --group dev

# 린트 + 포맷
uv run ruff check src tests
uv run ruff format src tests

# 타입 체크
uv run pyright

# 테스트 (브라우저 불필요)
uv run pytest tests/ -v
```

## 프로젝트 구조

```
src/
└── danawa_mcp/
    ├── __init__.py       # 버전 정보
    ├── server.py         # FastMCP 서버 + 도구 등록
    ├── browser.py        # Playwright 브라우저 + 네트워크 캡처
    ├── models.py         # Pydantic 데이터 모델
    └── tools/
        ├── categories.py # 카테고리 도구
        ├── products.py   # 제품 도구
        └── reviews.py    # 리뷰 도구
tests/
├── conftest.py           # 공유 픽스처
├── test_models.py        # 모델 단위 테스트
└── test_tools.py         # 파서 단위 테스트
```

## 라이선스

MIT License — [LICENSE](LICENSE) 파일 참조.
