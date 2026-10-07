"""Configuração administrativa e pré-validação da geofence mobile."""

from uuid import UUID

import psycopg2.extras
import requests
from flask import Blueprint, current_app, g, jsonify, request

from db import conectar_bd
from services.mobile_location import (
    LocationValidationError,
    TomTomClient,
    parse_location,
    validate_geofence,
)
from utils.auth_decorator import require_roles


mobile_location_bp = Blueprint("mobile_location", __name__)
MOBILE_ROLES = ("administrador", "funcionario", "gestor", "rh")


def _uuid(value, label):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} inválida.") from exc


def _tomtom():
    return TomTomClient(
        current_app.config.get("TOMTOM_API_KEY"),
        current_app.config.get("TOMTOM_TIMEOUT_SECONDS", 5),
    )


def _unit_for_employee(cursor):
    cursor.execute(
        """SELECT un.id, un.nome, un.latitude, un.longitude,
                  un.endereco_geocodificado, un.raio_metros,
                  un.marcacao_mobile_ativa
           FROM funcionarios f
           INNER JOIN unidades un
             ON un.id=f.unidade_id AND un.empresa_id=f.empresa_id
           WHERE f.id=%s AND f.empresa_id=%s AND f.status='ativo'
             AND un.status='ativa'""",
        (g.auth_funcionario_id, g.auth_context["empresa_id"]),
    )
    return cursor.fetchone()


def _serialize_unit(unit):
    return {
        "id": str(unit["id"]),
        "nome": unit["nome"],
        "latitude": unit.get("latitude"),
        "longitude": unit.get("longitude"),
        "endereco": unit.get("endereco_geocodificado"),
        "raio_metros": unit["raio_metros"],
        "marcacao_mobile_ativa": unit["marcacao_mobile_ativa"],
    }


def _audit_denied(cursor, unit, error, location_payload):
    metadata = {
        "motivo": error.code,
        "unidade_id": str(unit["id"]) if unit else None,
        "precisao_metros": location_payload.get("precisao_metros") if isinstance(location_payload, dict) else None,
        "simulada": bool(location_payload.get("simulada")) if isinstance(location_payload, dict) else False,
    }
    cursor.execute(
        """INSERT INTO auditoria (
               empresa_id, ator_usuario_id, acao, entidade_tipo,
               entidade_id, ocorrido_at, metadados
           ) VALUES (%s,%s,'marcacao.mobile.localizacao_rejeitada',
                     'funcionario',%s,clock_timestamp(),%s)""",
        (
            g.auth_context["empresa_id"],
            g.auth_context["user_id"],
            g.auth_funcionario_id,
            psycopg2.extras.Json(metadata),
        ),
    )


@mobile_location_bp.get("/api/mobile/marcacao/configuracao")
@require_roles(*MOBILE_ROLES)
def mobile_clock_configuration():
    connection = conectar_bd()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            unit = _unit_for_employee(cursor)
        if not unit:
            return jsonify({"erro": "Vínculo funcional não encontrado."}), 404
        return jsonify({"unidade": _serialize_unit(unit)}), 200
    finally:
        connection.close()


@mobile_location_bp.post("/api/mobile/localizacao/validar")
@require_roles(*MOBILE_ROLES)
def validate_mobile_location():
    payload = request.get_json(silent=True) or {}
    connection = conectar_bd()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            unit = _unit_for_employee(cursor)
            try:
                location = parse_location(payload)
                distance = validate_geofence(location, unit)
            except LocationValidationError as exc:
                _audit_denied(cursor, unit, exc, payload)
                connection.commit()
                return jsonify({"erro": str(exc), "codigo": exc.code}), exc.status

        address = None
        map_base64 = None
        try:
            client = _tomtom()
            address = client.reverse(location["latitude"], location["longitude"])
            map_base64 = client.static_map_base64(location["latitude"], location["longitude"])
        except (requests.RequestException, ValueError):
            current_app.logger.warning("TomTom indisponível durante a prévia mobile.", exc_info=True)
        return jsonify({
            "elegivel": True,
            "distancia_metros": round(distance, 1),
            "endereco": address,
            "mapa_png_base64": map_base64,
            "unidade": _serialize_unit(unit),
        }), 200
    finally:
        connection.close()


@mobile_location_bp.get("/api/admin/geocodificacao")
@require_roles("administrador")
def geocode_address():
    query = " ".join(str(request.args.get("q") or "").split())
    if len(query) < 3 or len(query) > 200:
        return jsonify({"erro": "Informe um endereço entre 3 e 200 caracteres."}), 400
    try:
        return jsonify({"resultados": _tomtom().search(query)}), 200
    except requests.RequestException:
        return jsonify({"erro": "O serviço de mapas está temporariamente indisponível."}), 503


@mobile_location_bp.get("/api/admin/geocodificacao/mapa")
@require_roles("administrador")
def admin_map_preview():
    try:
        latitude = float(request.args.get("latitude"))
        longitude = float(request.args.get("longitude"))
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError
        image = _tomtom().static_map_base64(latitude, longitude)
        if not image:
            return jsonify({"erro": "TomTom não está configurado."}), 503
        return jsonify({"mapa_png_base64": image, "zoom": 17}), 200
    except (TypeError, ValueError):
        return jsonify({"erro": "Coordenadas inválidas."}), 400
    except requests.RequestException:
        return jsonify({"erro": "O serviço de mapas está temporariamente indisponível."}), 503


@mobile_location_bp.get("/api/admin/unidades/<unit_id>/geofence")
@require_roles("administrador")
def get_unit_geofence(unit_id):
    try:
        identifier = _uuid(unit_id, "Unidade")
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    connection = conectar_bd()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """SELECT id,nome,latitude,longitude,endereco_geocodificado,
                          raio_metros,marcacao_mobile_ativa
                   FROM unidades WHERE id=%s AND empresa_id=%s""",
                (identifier, g.auth_context["empresa_id"]),
            )
            unit = cursor.fetchone()
        if not unit:
            return jsonify({"erro": "Unidade não encontrada."}), 404
        return jsonify({"unidade": _serialize_unit(unit)}), 200
    finally:
        connection.close()


@mobile_location_bp.put("/api/admin/unidades/<unit_id>/geofence")
@require_roles("administrador")
def update_unit_geofence(unit_id):
    connection = None
    try:
        identifier = _uuid(unit_id, "Unidade")
        payload = request.get_json(silent=True) or {}
        allowed = {"latitude", "longitude", "endereco", "raio_metros", "ativa"}
        if set(payload) - allowed:
            raise ValueError("A requisição contém campos não permitidos.")
        latitude = float(payload.get("latitude"))
        longitude = float(payload.get("longitude"))
        radius = int(payload.get("raio_metros", 150))
        address = " ".join(str(payload.get("endereco") or "").split()) or None
        active = payload.get("ativa") is True
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Coordenadas inválidas.")
        if not 25 <= radius <= 1000:
            raise ValueError("O raio deve estar entre 25 e 1000 metros.")
        if address and len(address) > 300:
            raise ValueError("Endereço excede 300 caracteres.")

        connection = conectar_bd()
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """UPDATE unidades
                   SET latitude=%s, longitude=%s, endereco_geocodificado=%s,
                       raio_metros=%s, marcacao_mobile_ativa=%s,
                       geofence_updated_at=clock_timestamp(), geofence_updated_by=%s,
                       updated_at=clock_timestamp()
                   WHERE id=%s AND empresa_id=%s
                   RETURNING id,nome,latitude,longitude,endereco_geocodificado,
                             raio_metros,marcacao_mobile_ativa""",
                (latitude, longitude, address, radius, active, g.auth_context["user_id"], identifier, g.auth_context["empresa_id"]),
            )
            unit = cursor.fetchone()
            if not unit:
                connection.rollback()
                return jsonify({"erro": "Unidade não encontrada."}), 404
            cursor.execute(
                """INSERT INTO auditoria (
                       empresa_id,ator_usuario_id,acao,entidade_tipo,entidade_id,
                       ocorrido_at,metadados
                   ) VALUES (%s,%s,'unidade.geofence_atualizada','unidade',%s,
                             clock_timestamp(),%s)""",
                (g.auth_context["empresa_id"], g.auth_context["user_id"], identifier,
                 psycopg2.extras.Json({"raio_metros": radius, "ativa": active})),
            )
        connection.commit()
        return jsonify({"unidade": _serialize_unit(unit)}), 200
    except (TypeError, ValueError) as exc:
        if connection:
            connection.rollback()
        return jsonify({"erro": str(exc)}), 400
    finally:
        if connection:
            connection.close()
