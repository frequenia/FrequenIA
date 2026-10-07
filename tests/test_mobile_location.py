import unittest
from datetime import datetime, timedelta, timezone

from services.mobile_location import (
    LocationValidationError,
    distance_meters,
    parse_location,
    validate_geofence,
)


NOW = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)


def payload(**overrides):
    value = {
        "latitude": -23.55052,
        "longitude": -46.633308,
        "precisao_metros": 12,
        "capturada_em": NOW.isoformat(),
        "simulada": False,
    }
    value.update(overrides)
    return value


def unit(**overrides):
    value = {
        "latitude": -23.55052,
        "longitude": -46.633308,
        "raio_metros": 150,
        "marcacao_mobile_ativa": True,
    }
    value.update(overrides)
    return value


class MobileLocationTests(unittest.TestCase):
    def test_accepts_precise_fresh_position_inside_geofence(self):
        location = parse_location(payload(), now=NOW)
        self.assertAlmostEqual(validate_geofence(location, unit()), 0, places=3)

    def test_boundary_distance_is_accepted(self):
        location = parse_location(payload(latitude=-23.549171), now=NOW)
        self.assertLessEqual(validate_geofence(location, unit(raio_metros=151)), 151)

    def test_rejects_inaccurate_mocked_stale_and_outside_positions(self):
        cases = [
            (payload(precisao_metros=50.1), "localizacao_imprecisa"),
            (payload(simulada=True), "localizacao_simulada"),
            (payload(capturada_em=(NOW - timedelta(seconds=121)).isoformat()), "localizacao_expirada"),
        ]
        for value, code in cases:
            with self.subTest(code=code), self.assertRaises(LocationValidationError) as raised:
                parse_location(value, now=NOW)
            self.assertEqual(raised.exception.code, code)
        with self.assertRaises(LocationValidationError) as raised:
            validate_geofence(parse_location(payload(latitude=-23.54), now=NOW), unit())
        self.assertEqual(raised.exception.code, "fora_do_perimetro")

    def test_disabled_unit_is_rejected(self):
        with self.assertRaises(LocationValidationError) as raised:
            validate_geofence(parse_location(payload(), now=NOW), unit(marcacao_mobile_ativa=False))
        self.assertEqual(raised.exception.code, "marcacao_mobile_desabilitada")

    def test_distance_is_symmetric(self):
        first = distance_meters(-23.55, -46.63, -23.56, -46.64)
        second = distance_meters(-23.56, -46.64, -23.55, -46.63)
        self.assertAlmostEqual(first, second)


if __name__ == "__main__":
    unittest.main()
