import datetime as dt
import logging
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class GeoInfo:
    def __init__(self, city: str, latitude: float, longitude: float, timezone: str):
        self.city = city
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = timezone


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
CURRENCY_URL = "https://api.exchangerate.host/latest"
BTC_URL = "https://api.coindesk.com/v1/bpi/currentprice/USD.json"


class WeatherService:
    @staticmethod
    def geocode(city: str) -> Optional[GeoInfo]:
        resp = requests.get(GEOCODE_URL, params={"name": city, "count": 1, "language": "ru"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("results"):
            logger.warning("Город '%s' не найден при геокодировании", city)
            return None
        first = data["results"][0]
        logger.info("Геокодирован город '%s' -> %s (%s)", city, first.get("name", city), first.get("timezone"))
        return GeoInfo(city=first.get("name", city), latitude=first["latitude"], longitude=first["longitude"], timezone=first["timezone"])

    @staticmethod
    def fetch_weather(geo: GeoInfo) -> Tuple[str, str]:
        params = {
            "latitude": geo.latitude,
            "longitude": geo.longitude,
            "current_weather": True,
            "hourly": "temperature_2m,weathercode",
            "timezone": geo.timezone,
            "forecast_days": 1,
        }
        resp = requests.get(WEATHER_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current_weather", {})
        hourly = data.get("hourly", {})
        temperature = current.get("temperature")
        windspeed = current.get("windspeed")
        weathercode = current.get("weathercode")
        code_map = {
            0: "ясно",
            1: "в основном ясно",
            2: "переменная облачность",
            3: "пасмурно",
            45: "туман",
            48: "изморозь",
            51: "легкая морось",
            53: "морось",
            55: "сильная морось",
            61: "слабый дождь",
            63: "дождь",
            65: "сильный дождь",
            71: "слабый снег",
            73: "снег",
            75: "сильный снег",
            95: "гроза",
        }
        code_text = code_map.get(weathercode, "погода уточняется")
        now_descr = f"🌡 {temperature}°C • 🌬 {windspeed} м/с • {code_text}"
        logger.info("Получена погода для %s: %s", geo.city, now_descr)

        today_summary = "Нет данных"
        if "temperature_2m" in hourly:
            temps = hourly.get("temperature_2m", [])
            today_summary = f"Мин/макс за день: {min(temps):.1f}/{max(temps):.1f}°C"
        return now_descr, today_summary


class CurrencyService:
    @staticmethod
    def fetch_currency() -> str:
        parts = ["💱 Курсы валют"]
        try:
            fx_resp = requests.get(CURRENCY_URL, params={"base": "USD", "symbols": "RUB,CNY"}, timeout=10)
            fx_resp.raise_for_status()
            fx_data = fx_resp.json()
            rates = fx_data.get("rates", {})
            rub = rates.get("RUB")
            cny = rates.get("CNY")
        except Exception as exc:  # pragma: no cover
            logger.warning("Не удалось получить курсы валют: %s", exc)
            rub = cny = None

        try:
            btc_resp = requests.get(BTC_URL, timeout=10)
            btc_resp.raise_for_status()
            btc_data = btc_resp.json()
            btc_usd = btc_data.get("bpi", {}).get("USD", {}).get("rate")
        except Exception as exc:  # pragma: no cover
            logger.warning("Не удалось получить курс BTC: %s", exc)
            btc_usd = None

        if rub is not None:
            parts.append(f"• USD → RUB: {rub:.2f}")
        if cny is not None:
            parts.append(f"• USD → CNY: {cny:.4f}")
        if btc_usd:
            parts.append(f"• BTC → USD: {btc_usd}")

        if len(parts) == 1:
            parts.append("Курсы временно недоступны.")
        else:
            logger.info("Курсы: %s", "; ".join(parts[1:]))

        return "\n".join(parts)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
