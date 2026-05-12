"""
Tool 2: DateTime (날짜/시간 조회)
=================================
인터넷 NTP 서버에서 정확한 현재 시간을 가져옵니다.
ntplib가 없거나 NTP 조회 실패 시 로컬 시스템 시간을 사용합니다.
"""

import sys
from datetime import datetime, timezone
from typing import Optional

import pytz

# ntplib는 선택적 의존성 (없어도 동작)
try:
    import ntplib
    _NTP_AVAILABLE = True
except ImportError:
    _NTP_AVAILABLE = False


# NTP 서버 풀 (여러 서버로 폴백)
NTP_SERVERS = [
    "pool.ntp.org",
    "time.google.com",
    "time.cloudflare.com",
    "time.windows.com",
]


def _get_ntp_time() -> Optional[datetime]:
    """NTP 서버에서 UTC 시간을 가져옵니다."""
    if not _NTP_AVAILABLE:
        return None

    client = ntplib.NTPClient()
    for server in NTP_SERVERS:
        try:
            response = client.request(server, version=3, timeout=3)
            return datetime.fromtimestamp(response.tx_time, tz=timezone.utc)
        except Exception:
            continue
    return None


def get_current_datetime(timezone_str: str = "Asia/Seoul") -> dict:
    """
    현재 날짜와 시간을 반환합니다. NTP 서버에서 정확한 시간을 조회합니다.

    Args:
        timezone_str: 타임존 문자열 (IANA 형식, 예: "Asia/Seoul", "UTC", "America/New_York")
                      기본값은 한국 표준시 (KST, UTC+9)

    Returns:
        날짜, 시간, 타임존 정보를 담은 딕셔너리
    """
    # 타임존 유효성 검사
    try:
        tz = pytz.timezone(timezone_str)
    except pytz.exceptions.UnknownTimeZoneError:
        return {
            "error": f"알 수 없는 타임존: {timezone_str}. "
                     "예시: Asia/Seoul, UTC, America/New_York, Europe/London",
            "available_example": list(pytz.common_timezones[:10]),
        }

    # 시간 소스 결정 (NTP 우선, 실패 시 로컬)
    source = "local_system"
    utc_now = None

    if _NTP_AVAILABLE:
        utc_now = _get_ntp_time()
        if utc_now:
            source = "ntp_internet"

    if utc_now is None:
        utc_now = datetime.now(timezone.utc)

    # 타임존 변환
    local_now = utc_now.astimezone(tz)

    # 요일 (한국어)
    weekday_ko = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    weekday_en = local_now.strftime("%A")

    # UTC 오프셋 계산
    utc_offset = local_now.utcoffset()
    total_seconds = int(utc_offset.total_seconds())
    offset_hours = total_seconds // 3600
    offset_minutes = (total_seconds % 3600) // 60
    offset_str = f"UTC{'+' if offset_hours >= 0 else ''}{offset_hours:02d}:{offset_minutes:02d}"

    return {
        "timezone": timezone_str,
        "date": local_now.strftime("%Y년 %m월 %d일"),
        "date_iso": local_now.strftime("%Y-%m-%d"),
        "time": local_now.strftime("%H시 %M분 %S초"),
        "time_iso": local_now.strftime("%H:%M:%S"),
        "datetime_full": local_now.strftime("%Y년 %m월 %d일 %H시 %M분 %S초"),
        "datetime_iso": local_now.isoformat(),
        "weekday_korean": weekday_ko[local_now.weekday()],
        "weekday_english": weekday_en,
        "utc_offset": offset_str,
        "utc_time": utc_now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "time_source": source,
        "ntp_available": _NTP_AVAILABLE,
    }


def list_timezones(region: str = "Asia") -> dict:
    """
    특정 지역의 타임존 목록을 반환합니다.

    Args:
        region: 지역 필터 (예: "Asia", "America", "Europe", "all")

    Returns:
        타임존 목록
    """
    if region.lower() == "all":
        tzones = pytz.common_timezones
    else:
        tzones = [tz for tz in pytz.common_timezones if tz.startswith(region)]

    return {
        "region": region,
        "count": len(tzones),
        "timezones": tzones[:50],  # 최대 50개
    }


# ─────────────────────────────────────────────────
# 모듈 단독 실행 테스트
# ─────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    print("=== 현재 시간 조회 (KST) ===")
    result = get_current_datetime("Asia/Seoul")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n=== 현재 시간 조회 (UTC) ===")
    result = get_current_datetime("UTC")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n=== 잘못된 타임존 ===")
    result = get_current_datetime("Invalid/Zone")
    print(json.dumps(result, ensure_ascii=False, indent=2))
