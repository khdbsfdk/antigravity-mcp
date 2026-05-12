"""
Tool 3: Weather (날씨 조회)
=================================
OpenWeatherMap API를 사용하여 도시의 현재 날씨 정보를 가져옵니다.

API 키 발급: https://home.openweathermap.org/users/sign_up (무료)
환경변수: OPENWEATHER_API_KEY
"""

import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# OpenWeatherMap API 설정
OWM_BASE_URL = "http://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "http://api.openweathermap.org/data/2.5/forecast"

# 날씨 상태 이모지 매핑
WEATHER_EMOJI = {
    "clear sky": "☀️",
    "few clouds": "🌤️",
    "scattered clouds": "⛅",
    "broken clouds": "☁️",
    "overcast clouds": "☁️",
    "light rain": "🌦️",
    "moderate rain": "🌧️",
    "heavy intensity rain": "⛈️",
    "shower rain": "🌧️",
    "thunderstorm": "⛈️",
    "snow": "❄️",
    "light snow": "🌨️",
    "mist": "🌫️",
    "fog": "🌫️",
    "haze": "🌫️",
    "dust": "🌪️",
}

# 풍향 변환 (방위각 → 문자)
def _degrees_to_direction(degrees: float) -> str:
    """풍향 각도를 방위 문자열로 변환합니다."""
    directions = ["북", "북북동", "북동", "동북동", "동", "동남동", "남동", "남남동",
                  "남", "남남서", "남서", "서남서", "서", "서북서", "북서", "북북서"]
    idx = round(degrees / 22.5) % 16
    return directions[idx]


def get_weather(city: str, units: str = "metric", lang: str = "kr") -> dict:
    """
    지정한 도시의 현재 날씨 정보를 가져옵니다.

    Args:
        city: 도시 이름 (영문 또는 한국어, 예: "Seoul", "서울", "Tokyo", "New York")
        units: 온도 단위 ("metric" = 섭씨, "imperial" = 화씨, "standard" = 켈빈)
               기본값: "metric" (섭씨)
        lang: 날씨 설명 언어 ("kr" = 한국어, "en" = 영어)
               기본값: "kr"

    Returns:
        날씨 정보를 담은 딕셔너리
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY", "")

    if not api_key or api_key == "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
        return {
            "error": "OpenWeatherMap API 키가 설정되지 않았습니다.",
            "guide": "1. https://home.openweathermap.org/users/sign_up 에서 무료 가입 후 API 키 발급\n"
                     "2. .env 파일에 OPENWEATHER_API_KEY=<발급받은 키> 를 설정하세요.",
            "city": city,
        }

    unit_symbols = {"metric": "°C", "imperial": "°F", "standard": "K"}
    unit_symbol = unit_symbols.get(units, "°C")

    params = {
        "q": city,
        "appid": api_key,
        "units": units,
        "lang": lang,
    }

    try:
        response = requests.get(OWM_BASE_URL, params=params, timeout=10)

        if response.status_code == 401:
            return {
                "error": "API 키가 유효하지 않습니다. API 키를 확인하거나 활성화 대기 중(10~15분)일 수 있습니다.",
                "city": city,
            }
        elif response.status_code == 404:
            return {
                "error": f"도시를 찾을 수 없습니다: '{city}'. 영문 도시명으로 다시 시도해보세요.",
                "city": city,
            }
        elif response.status_code == 429:
            return {
                "error": "API 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.",
                "city": city,
            }

        response.raise_for_status()
        data = response.json()

        # 데이터 파싱
        main = data["main"]
        weather_info = data["weather"][0]
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        sys_info = data.get("sys", {})
        visibility = data.get("visibility", None)

        weather_desc = weather_info.get("description", "")
        weather_main_en = weather_info.get("main", "").lower()
        emoji = WEATHER_EMOJI.get(weather_desc.lower(),
                WEATHER_EMOJI.get(weather_main_en, "🌡️"))

        # 풍속 정보
        wind_speed = wind.get("speed", 0)
        wind_deg = wind.get("deg", None)
        wind_direction = _degrees_to_direction(wind_deg) if wind_deg is not None else "정보없음"
        wind_gust = wind.get("gust", None)

        # 일출/일몰 시간 (현지 UTC 기준)
        from datetime import datetime, timezone
        sunrise = datetime.fromtimestamp(sys_info.get("sunrise", 0), tz=timezone.utc).strftime("%H:%M UTC")
        sunset = datetime.fromtimestamp(sys_info.get("sunset", 0), tz=timezone.utc).strftime("%H:%M UTC")

        result = {
            "city": data["name"],
            "country": sys_info.get("country", ""),
            "coordinates": {
                "lat": data["coord"]["lat"],
                "lon": data["coord"]["lon"],
            },
            "weather": {
                "status": weather_info.get("main", ""),
                "description": weather_desc,
                "emoji": emoji,
            },
            "temperature": {
                "current": f"{main['temp']}{unit_symbol}",
                "feels_like": f"{main['feels_like']}{unit_symbol}",
                "min": f"{main['temp_min']}{unit_symbol}",
                "max": f"{main['temp_max']}{unit_symbol}",
            },
            "humidity": f"{main['humidity']}%",
            "pressure": f"{main['pressure']} hPa",
            "visibility": f"{visibility // 1000} km" if visibility else "정보없음",
            "wind": {
                "speed": f"{wind_speed} m/s",
                "direction": wind_direction,
                "gust": f"{wind_gust} m/s" if wind_gust else "정보없음",
            },
            "clouds": f"{clouds.get('cloudiness', clouds.get('all', 0))}%",
            "sun": {
                "sunrise": sunrise,
                "sunset": sunset,
            },
            "units": units,
            "summary": (
                f"{data['name']}({sys_info.get('country', '')})의 현재 날씨: "
                f"{emoji} {weather_desc}, "
                f"기온 {main['temp']}{unit_symbol} (체감 {main['feels_like']}{unit_symbol}), "
                f"습도 {main['humidity']}%"
            ),
        }

        return result

    except requests.exceptions.ConnectionError:
        return {
            "error": "네트워크 연결 오류입니다. 인터넷 연결을 확인해주세요.",
            "city": city,
        }
    except requests.exceptions.Timeout:
        return {
            "error": "API 요청 시간이 초과되었습니다. 다시 시도해주세요.",
            "city": city,
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"API 요청 오류: {str(e)}", "city": city}
    except Exception as e:
        return {"error": f"예상치 못한 오류: {str(e)}", "city": city}


def search_cities(city_name: str) -> dict:
    """
    도시 이름으로 좌표 정보를 검색합니다 (Geocoding API 사용).

    Args:
        city_name: 검색할 도시 이름

    Returns:
        도시 후보 목록
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY", "")
    if not api_key or api_key == "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx":
        return {"error": "API 키가 설정되지 않았습니다.", "query": city_name}

    geocode_url = "http://api.openweathermap.org/geo/1.0/direct"
    params = {"q": city_name, "limit": 5, "appid": api_key}

    try:
        response = requests.get(geocode_url, params=params, timeout=10)
        response.raise_for_status()
        results = response.json()
        return {
            "query": city_name,
            "results": [
                {
                    "name": r.get("name"),
                    "country": r.get("country"),
                    "state": r.get("state", ""),
                    "lat": r.get("lat"),
                    "lon": r.get("lon"),
                }
                for r in results
            ],
        }
    except Exception as e:
        return {"error": str(e), "query": city_name}


# ─────────────────────────────────────────────────
# 모듈 단독 실행 테스트
# ─────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    cities = ["Seoul", "Tokyo", "London"]
    for city in cities:
        print(f"\n=== {city} 날씨 ===")
        result = get_weather(city)
        print(json.dumps(result, ensure_ascii=False, indent=2))
