import datetime as dt
from typing import Optional, Tuple

import requests


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
            return None
        first = data["results"][0]
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

        today_summary = "Нет данных"
        if "temperature_2m" in hourly:
            temps = hourly.get("temperature_2m", [])
            today_summary = f"Мин/макс за день: {min(temps):.1f}/{max(temps):.1f}°C"
        return now_descr, today_summary


class CurrencyService:
    @staticmethod
    def fetch_currency() -> str:
        fx_resp = requests.get(CURRENCY_URL, params={"base": "USD", "symbols": "RUB,CNY"}, timeout=10)
        fx_resp.raise_for_status()
        fx_data = fx_resp.json()
        rates = fx_data.get("rates", {})
        rub = rates.get("RUB")
        cny = rates.get("CNY")

        btc_resp = requests.get(BTC_URL, timeout=10)
        btc_resp.raise_for_status()
        btc_data = btc_resp.json()
        btc_usd = btc_data.get("bpi", {}).get("USD", {}).get("rate")
        if rub is None or cny is None or not btc_usd:
            return "💱 Курсы временно недоступны."
        return (
            "💱 Курсы валют и BTC:\n"
            f"• USD → RUB: {rub:.2f}\n"
            f"• USD → CNY: {cny:.4f}\n"
            f"• BTC → USD: {btc_usd}"
        )


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
