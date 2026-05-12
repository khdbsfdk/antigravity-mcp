"""
MCP Server - FastMCP 기반 도구 서버
=====================================
세 가지 Tool을 제공하는 MCP 서버입니다:

  - calculator      : 수식 계산 (사칙연산, 거듭제곱 등)
  - calculator_two  : 두 숫자 직접 연산
  - get_datetime    : 인터넷 시간/날짜 조회 (NTP)
  - list_timezones  : 타임존 목록 조회
  - get_weather     : 날씨 정보 조회 (OpenWeatherMap)
  - search_cities   : 도시 검색 (Geocoding)

실행 방법:
  # stdio 모드 (기본, Claude Desktop 등 로컬 클라이언트용)
  python server/server.py

  # HTTP 모드 (원격 접속, OpenShift/Kubernetes 배포용)
  python server/server.py --transport http --port 8080

  # MCP Inspector로 디버깅
  fastmcp dev server/server.py
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# 현재 파일 위치 기준으로 상위 폴더를 sys.path에 추가 (상대 임포트 지원)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.tools.calculator import calculate, calculate_two_numbers
from server.tools.datetime_tool import get_current_datetime, list_timezones
from server.tools.weather import get_weather, search_cities
from server.tools.ocr import extract_text_from_image, extract_text_from_directory
from server.tools.file_utils import read_text_file, list_directory_files

# 환경변수 로드
load_dotenv()

# 로깅 설정 (stdio 모드에서는 stderr로 출력해야 MCP 통신과 충돌 없음)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp-server")

# ─────────────────────────────────────────────────
# FastMCP 서버 초기화
# ─────────────────────────────────────────────────
mcp = FastMCP(
    name="mcp-tools-server",
    # 서버 설명 (MCP Inspector 등에서 표시됨)
    instructions=(
        "이 서버는 다섯 가지 도구 그룹을 제공합니다:\n"
        "1. 수학 계산기 (calculator): 수식 및 사칙연산 계산\n"
        "2. 날짜/시간 조회 (get_datetime): 인터넷 NTP 기반 정확한 현재 시간\n"
        "3. 날씨 정보 (weather): OpenWeatherMap 기반 실시간 날씨 조회\n"
        "4. OCR (ocr_extract): GPT-4o Vision 기반 이미지→텍스트 추출\n"
        "5. 파일 (read_file, list_files): 파일 읽기 및 디렉토리 탐색"
    ),
    # Kubernetes/OpenShift 내부 Service DNS 허용을 위해 host 패턴 무제한
    # FastMCP SSE의 Request validation이 Host 헤더를 검증하는데
    # 클러스터 내 DNS(mcp-tools-server.test.svc.cluster.local)를 허용하기 위함
    host="0.0.0.0",
    port=8080,
)

# FastMCP SSE Host 검증 완전 비활성화
# connect_sse()가 내부적으로 request.url.hostname을 검증하므로
# settings를 통해 allowed hosts를 override
try:
    # FastMCP 3.x: settings.allowed_hosts 또는 host 패턴 설정
    if hasattr(mcp, 'settings'):
        if hasattr(mcp.settings, 'host'):
            mcp.settings.host = "0.0.0.0"
except Exception:
    pass


# ─────────────────────────────────────────────────
# Tool 1: 수식 계산기
# ─────────────────────────────────────────────────
@mcp.tool()
def calculator(expression: str) -> str:
    """
    수학 수식을 계산합니다.

    지원하는 연산:
    - 기본 사칙연산: +, -, *, /
    - 거듭제곱: ** 또는 ^
    - 괄호: ()
    - 나머지: %
    - 수학 함수: sqrt(), abs(), round(), floor(), ceil()

    사용 예시:
    - "3 + 4 * 2"
    - "(10 - 5) ** 2"
    - "sqrt(144)"
    - "100 / 4 + 3 * 7"

    Args:
        expression: 계산할 수식 문자열

    Returns:
        계산 결과 문자열
    """
    logger.info(f"[calculator] expression={expression!r}")
    result = calculate(expression)

    if result.get("error"):
        return f"❌ 계산 오류: {result['error']}"

    return f"✅ {result['result_str']}"


@mcp.tool()
def calculator_two(a: float, b: float, operation: str) -> str:
    """
    두 숫자에 대해 사칙연산을 수행합니다.

    지원 연산 기호:
    - "+" : 덧셈
    - "-" : 뺄셈
    - "*" 또는 "×" : 곱셈
    - "/" 또는 "÷" : 나눗셈
    - "**" 또는 "^" : 거듭제곱
    - "%" : 나머지

    Args:
        a: 첫 번째 숫자
        b: 두 번째 숫자
        operation: 연산 기호 (예: "+", "-", "*", "/")

    Returns:
        계산 결과 문자열
    """
    logger.info(f"[calculator_two] a={a}, b={b}, op={operation!r}")
    result = calculate_two_numbers(a, b, operation)

    if result.get("error"):
        return f"❌ 계산 오류: {result['error']}"

    return f"✅ {result['result_str']}"


# ─────────────────────────────────────────────────
# Tool 2: 날짜/시간 조회
# ─────────────────────────────────────────────────
@mcp.tool()
def get_datetime(timezone: str = "Asia/Seoul") -> str:
    """
    현재 날짜와 시간을 조회합니다.
    인터넷 NTP 서버(pool.ntp.org)에서 정확한 시간을 가져옵니다.
    NTP 조회 실패 시 시스템 시간을 사용합니다.

    Args:
        timezone: IANA 타임존 문자열 (기본값: "Asia/Seoul" = 한국 표준시)
                  예시:
                  - "Asia/Seoul"      → 한국 (KST, UTC+9)
                  - "UTC"             → 협정 세계시
                  - "America/New_York"→ 미국 동부 시간
                  - "Europe/London"   → 영국 시간
                  - "Asia/Tokyo"      → 일본 표준시

    Returns:
        날짜, 시간, 요일, 타임존 오프셋 정보를 포함한 문자열
    """
    logger.info(f"[get_datetime] timezone={timezone!r}")
    result = get_current_datetime(timezone)

    if result.get("error"):
        return f"❌ 시간 조회 오류: {result['error']}"

    source_icon = "🌐" if result["time_source"] == "ntp_internet" else "🖥️"
    return (
        f"{source_icon} 현재 시간 ({result['timezone']})\n"
        f"📅 날짜: {result['date']} ({result['weekday_korean']})\n"
        f"⏰ 시간: {result['time']}\n"
        f"🌍 UTC 기준: {result['utc_time']}\n"
        f"📌 오프셋: {result['utc_offset']}\n"
        f"📡 시간 출처: {'NTP 인터넷 서버' if result['time_source'] == 'ntp_internet' else '로컬 시스템'}"
    )


@mcp.tool()
def get_timezones(region: str = "Asia") -> str:
    """
    특정 지역의 타임존 목록을 조회합니다.

    Args:
        region: 지역 이름 (예: "Asia", "America", "Europe", "all")

    Returns:
        타임존 목록 문자열
    """
    logger.info(f"[get_timezones] region={region!r}")
    result = list_timezones(region)

    if result.get("error"):
        return f"❌ 오류: {result['error']}"

    tz_list = "\n".join(f"  - {tz}" for tz in result["timezones"])
    return f"🌏 {region} 지역 타임존 ({result['count']}개):\n{tz_list}"


# ─────────────────────────────────────────────────
# Tool 3: 날씨 조회
# ─────────────────────────────────────────────────
@mcp.tool()
def weather(city: str, units: str = "metric") -> str:
    """
    지정한 도시의 현재 날씨 정보를 조회합니다.
    OpenWeatherMap API를 사용합니다.

    API 키 설정 필요: .env 파일에 OPENWEATHER_API_KEY 설정
    (https://home.openweathermap.org/users/sign_up 에서 무료 발급)

    Args:
        city: 도시 이름 (영문 권장, 예: "Seoul", "Tokyo", "London", "New York")
              한국어도 지원: "서울", "부산", "제주"
        units: 온도 단위
               - "metric"   : 섭씨 °C (기본값)
               - "imperial" : 화씨 °F
               - "standard" : 켈빈 K

    Returns:
        날씨 정보 (기온, 날씨 상태, 습도, 풍속 등)를 포함한 문자열
    """
    logger.info(f"[weather] city={city!r}, units={units!r}")
    result = get_weather(city, units)

    if result.get("error"):
        guide = result.get("guide", "")
        return f"❌ 날씨 조회 오류: {result['error']}" + (f"\n\n{guide}" if guide else "")

    w = result["weather"]
    t = result["temperature"]
    wind = result["wind"]
    sun = result["sun"]

    return (
        f"{w['emoji']} {result['city']}, {result['country']} 현재 날씨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌡️  날씨 상태: {w['description']}\n"
        f"🌡️  현재 기온: {t['current']} (체감 {t['feels_like']})\n"
        f"📊 최저/최고: {t['min']} / {t['max']}\n"
        f"💧 습도: {result['humidity']}\n"
        f"🔬 기압: {result['pressure']}\n"
        f"👁️  가시거리: {result['visibility']}\n"
        f"💨 바람: {wind['speed']} ({wind['direction']}풍){', 돌풍 ' + wind['gust'] if wind['gust'] != '정보없음' else ''}\n"
        f"☁️  구름량: {result['clouds']}\n"
        f"🌅 일출: {sun['sunrise']} | 🌇 일몰: {sun['sunset']}"
    )


@mcp.tool()
def find_city(city_name: str) -> str:
    """
    도시 이름으로 위치를 검색합니다. 동명이인 도시가 여러 개일 때 확인용으로 사용합니다.

    Args:
        city_name: 검색할 도시 이름

    Returns:
        도시 후보 목록 (국가, 위도/경도 포함)
    """
    logger.info(f"[find_city] city_name={city_name!r}")
    result = search_cities(city_name)

    if result.get("error"):
        return f"❌ 도시 검색 오류: {result['error']}"

    if not result.get("results"):
        return f"'{city_name}' 검색 결과가 없습니다."

    lines = [f"🔍 '{city_name}' 검색 결과:"]
    for i, r in enumerate(result["results"], 1):
        state = f", {r['state']}" if r.get("state") else ""
        lines.append(f"  {i}. {r['name']}{state} ({r['country']}) - 위도 {r['lat']:.2f}, 경도 {r['lon']:.2f}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────
# Tool 4: OCR (이미지 텍스트 추출)
# ─────────────────────────────────────────────────
@mcp.tool()
def ocr_extract(image_path: str = "", directory_path: str = "", output_path: str = "") -> str:
    """
    이미지에서 텍스트를 추출합니다 (OCR). GPT-4o Vision API를 사용합니다.

    두 가지 모드로 동작합니다:
    1. 단일 이미지 모드: image_path에 이미지 파일 경로를 지정
    2. 디렉토리 모드: directory_path에 이미지가 있는 폴더 경로를 지정
       → 폴더 내 모든 이미지를 일괄 OCR하고 결과를 텍스트 파일로 저장

    지원 이미지 형식: jpg, jpeg, png, gif, bmp, webp, tiff

    Args:
        image_path: 단일 이미지 파일 경로 (예: "/data/images/page1.jpg")
        directory_path: 이미지가 있는 디렉토리 경로 (예: "/data/images")
        output_path: (디렉토리 모드) 결과 저장 파일 경로. 비워두면 자동 생성

    Returns:
        OCR 추출 결과 또는 처리 요약
    """
    logger.info(f"[ocr_extract] image_path={image_path!r}, directory_path={directory_path!r}")

    # 디렉토리 모드
    if directory_path:
        result = extract_text_from_directory(
            directory_path,
            output_path if output_path else None,
        )
        if result.get("error"):
            return f"❌ OCR 오류: {result['error']}"
        return (
            f"✅ OCR 완료!\n"
            f"📁 소스: {directory_path}\n"
            f"📄 처리: {result['total_images']}개 이미지 → 성공 {result['success_count']}개\n"
            f"💾 결과 파일: {result['output_file']}\n"
            f"📋 처리된 파일: {', '.join(result['processed_files'])}"
        )

    # 단일 이미지 모드
    if image_path:
        result = extract_text_from_image(image_path)
        if result.get("error"):
            return f"❌ OCR 오류: {result['error']}"
        return (
            f"✅ OCR 완료 ({result['file']})\n"
            f"📊 사용 토큰: {result.get('tokens_used', 'N/A')}\n\n"
            f"--- 추출된 텍스트 ---\n{result['text']}"
        )

    return "❌ image_path 또는 directory_path 중 하나를 지정해주세요."


# ─────────────────────────────────────────────────
# Tool 5: 파일 유틸리티
# ─────────────────────────────────────────────────
@mcp.tool()
def read_file(file_path: str) -> str:
    """
    텍스트 파일의 내용을 읽어 반환합니다.
    OCR로 생성된 결과 파일이나 기타 텍스트 파일을 읽을 때 사용합니다.

    Args:
        file_path: 읽을 파일의 경로 (예: "/data/images/ocr_result.txt")

    Returns:
        파일 내용 문자열
    """
    logger.info(f"[read_file] file_path={file_path!r}")
    result = read_text_file(file_path)

    if result.get("error"):
        return f"❌ 파일 읽기 오류: {result['error']}"

    return (
        f"📄 {result['file']} ({result['size_bytes']:,} bytes, {result['line_count']}줄)\n"
        f"{'─'*40}\n"
        f"{result['content']}"
    )


@mcp.tool()
def list_files(directory_path: str, extension_filter: str = "") -> str:
    """
    디렉토리 내 파일 목록을 조회합니다.
    이미지 파일이나 OCR 결과 파일이 있는지 확인할 때 사용합니다.

    Args:
        directory_path: 조회할 디렉토리 경로 (예: "/data/images")
        extension_filter: 특정 확장자만 필터 (예: ".txt", ".jpg"). 비워두면 전체 표시

    Returns:
        파일 목록 문자열
    """
    logger.info(f"[list_files] directory_path={directory_path!r}, filter={extension_filter!r}")
    result = list_directory_files(
        directory_path,
        extension_filter if extension_filter else None,
    )

    if result.get("error"):
        return f"❌ 디렉토리 조회 오류: {result['error']}"

    lines = [f"📂 {result['directory']} (폴더 {result['total_dirs']}개, 파일 {result['total_files']}개)"]

    for d in result["directories"]:
        lines.append(f"  📁 {d['name']}/")
    for f in result["files"]:
        size_kb = f['size_bytes'] / 1024
        lines.append(f"  📄 {f['name']}  ({size_kb:.1f} KB, {f['modified']})")

    if not result["directories"] and not result["files"]:
        lines.append("  (비어 있음)")

    return "\n".join(lines)


# ─────────────────────────────────────────────────
# 서버 실행 진입점
# ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="MCP Tools Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
실행 예시:
  python server/server.py                    # stdio 모드 (기본)
  python server/server.py --transport http   # HTTP 모드 (포트 8080)
  python server/server.py --transport http --port 9000  # HTTP 다른 포트
        """,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport 방식 (기본값: stdio)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_SERVER_HOST", "0.0.0.0"),
        help="HTTP 모드에서 바인딩할 호스트 (기본값: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_SERVER_PORT", "8080")),
        help="HTTP 모드에서 사용할 포트 (기본값: 8080)",
    )

    args = parser.parse_args()

    logger.info(f"MCP Tools Server 시작 (transport={args.transport})")
    logger.info(f"등록된 도구: calculator, calculator_two, get_datetime, get_timezones, weather, find_city")

    if args.transport == "stdio":
        logger.info("stdio 모드로 실행 중 (Claude Desktop, MCP Inspector 등)")
        mcp.run(transport="stdio")
    else:
        logger.info(f"SSE HTTP 모드로 실행 중: http://{args.host}:{args.port}")
        logger.info("DNS rebinding protection 비활성화 (Kubernetes 내부 통신)")
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        from mcp.server.sse import SseServerTransport

        # FastMCP 1.27+ SSE 서버는 host="127.0.0.1"일 때만 DNS rebinding protection ON
        # host="0.0.0.0"이면 보안 설정 없이 실행됨 → 외부 Host 헤더 허용
        # SseServerTransport를 직접 생성: transport_security=None → 검증 완전 비활성화
        sse_transport = SseServerTransport(
            endpoint="/messages",
            security_settings=None,  # DNS rebinding protection 완전 비활성화
        )

        async def handle_sse(request):
            async with sse_transport.connect_sse(
                request.scope, request.receive, request._send
            ) as (read_stream, write_stream):
                await mcp._mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp._mcp_server.create_initialization_options(),
                )

        from starlette.requests import Request
        from starlette.responses import Response

        starlette_app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages", app=sse_transport.handle_post_message),
            ]
        )

        logger.info(f"Starlette SSE 앱 시작: 0.0.0.0:{args.port}")
        logger.info("  GET  /sse      → SSE 이벤트 스트림")
        logger.info("  POST /messages → 메시지 전송")

        uvicorn.run(
            starlette_app,
            host=args.host,
            port=args.port,
            forwarded_allow_ips="*",
            proxy_headers=True,
        )


if __name__ == "__main__":
    main()
