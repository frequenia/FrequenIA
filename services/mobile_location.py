"""Validação autoritativa de geofence e integração auxiliar com TomTom."""

from base64 import b64encode
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from urllib.parse import quote

import requests


MAX_ACCURACY_METERS = 50.0
MAX_LOCATION_AGE_SECONDS = 120
MAX_FUTURE_SKEW_SECONDS = 15


class LocationValidationError(ValueError):
    def __init__(self, message, code, status=422):
        super().__init__(message)
        self.code = code
        self.status = status


def _number(value, field, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise LocationValidationError(f"{field} inválida.", "localizacao_invalida", 400) from exc
    if not minimum <= parsed <= maximum:
        raise LocationValidationError(f"{field} inválida.", "localizacao_invalida", 400)
    return parsed


def parse_location(payload, *, now=None):
    if not isinstance(payload, dict):
        raise LocationValidationError("Localização é obrigatória.", "localizacao_obrigatoria", 400)
    latitude = _number(payload.get("latitude"), "Latitude", -90, 90)
    longitude = _number(payload.get("longitude"), "Longitude", -180, 180)
    accuracy = _number(payload.get("precisao_metros"), "Precisão", 0, 100000)
    if payload.get("simulada") is True:
        raise LocationValidationError("Localização simulada não é permitida.", "localizacao_simulada", 403)
    if accuracy > MAX_ACCURACY_METERS:
        raise LocationValidationError(
            "A localização está imprecisa. Vá para uma área aberta e tente novamente.",
            "localizacao_imprecisa",
        )
    raw_captured = str(payload.get("capturada_em") or "")
    try:
        captured_at = datetime.fromisoformat(raw_captured.replace("Z", "+00:00"))
        if captured_at.tzinfo is None:
            raise ValueError
        captured_at = captured_at.astimezone(timezone.utc)
    except ValueError as exc:
        raise LocationValidationError("Horário da localização inválido.", "localizacao_invalida", 400) from exc
    reference = now or datetime.now(timezone.utc)
    age = (reference - captured_at).total_seconds()
    if age < -MAX_FUTURE_SKEW_SECONDS or age > MAX_LOCATION_AGE_SECONDS:
        raise LocationValidationError("A localização expirou. Obtenha uma nova posição.", "localizacao_expirada", 409)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "precisao_metros": accuracy,
        "capturada_at": captured_at,
    }


def distance_meters(lat1, lon1, lat2, lon2):
    earth_radius = 6371008.8
    phi1, phi2 = radians(lat1), radians(lat2)
    delta_phi = radians(lat2 - lat1)
    delta_lambda = radians(lon2 - lon1)
    a = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    return earth_radius * 2 * asin(sqrt(a))


def validate_geofence(location, unit):
    if not unit or not unit.get("marcacao_mobile_ativa"):
        raise LocationValidationError(
            "A marcação pelo celular não está habilitada para sua unidade.",
            "marcacao_mobile_desabilitada",
            403,
        )
    if unit.get("latitude") is None or unit.get("longitude") is None:
        raise LocationValidationError("A unidade não possui geofence configurada.", "geofence_nao_configurada", 409)
    distance = distance_meters(
        location["latitude"], location["longitude"], float(unit["latitude"]), float(unit["longitude"])
    )
    if distance > float(unit["raio_metros"]):
        raise LocationValidationError(
            "Você está fora do perímetro permitido para esta unidade.",
            "fora_do_perimetro",
            403,
        )
    return distance


class TomTomClient:
    def __init__(self, api_key, timeout=5):
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    @property
    def available(self):
        return bool(self.api_key)

    def search(self, query, limit=5):
        if not self.available:
            return []
        response = requests.get(
            f"https://api.tomtom.com/search/2/geocode/{quote(query, safe='')}.json",
            params={"key": self.api_key, "limit": limit, "language": "pt-BR", "countrySet": "BR"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = []
        for item in response.json().get("results", []):
            position = item.get("position") or {}
            address = item.get("address") or {}
            if position.get("lat") is None or position.get("lon") is None:
                continue
            results.append({
                "endereco": address.get("freeformAddress") or item.get("poi", {}).get("name") or query,
                "latitude": position["lat"],
                "longitude": position["lon"],
            })
        return results

    def reverse(self, latitude, longitude):
        if not self.available:
            return None
        response = requests.get(
            f"https://api.tomtom.com/search/2/reverseGeocode/{latitude},{longitude}.json",
            params={"key": self.api_key, "language": "pt-BR"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        addresses = response.json().get("addresses", [])
        if not addresses:
            return None
        return (addresses[0].get("address") or {}).get("freeformAddress")

    def static_map_base64(self, latitude, longitude, width=640, height=320):
        if not self.available:
            return None
        response = requests.get(
            "https://api.tomtom.com/map/1/staticimage",
            params={
                "key": self.api_key,
                "center": f"{longitude},{latitude}",
                "zoom": 17,
                "width": width,
                "height": height,
                "format": "png",
                "layer": "basic",
                "style": "main",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return b64encode(response.content).decode("ascii")
