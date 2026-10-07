import 'dart:convert';
import 'dart:typed_data';

import 'package:geolocator/geolocator.dart';

import '../core/api_client.dart';

class MobileLocationSnapshot {
  const MobileLocationSnapshot({
    required this.latitude,
    required this.longitude,
    required this.accuracyMeters,
    required this.capturedAt,
    required this.isMocked,
  });

  final double latitude;
  final double longitude;
  final double accuracyMeters;
  final DateTime capturedAt;
  final bool isMocked;

  Map<String, dynamic> toJson() => {
    'latitude': latitude,
    'longitude': longitude,
    'precisao_metros': accuracyMeters,
    'capturada_em': capturedAt.toUtc().toIso8601String(),
    'simulada': isMocked,
  };
}

class MobileLocationPreview {
  const MobileLocationPreview({
    required this.snapshot,
    required this.distanceMeters,
    required this.unitName,
    required this.radiusMeters,
    this.address,
    this.mapBytes,
  });

  final MobileLocationSnapshot snapshot;
  final double distanceMeters;
  final String unitName;
  final int radiusMeters;
  final String? address;
  final Uint8List? mapBytes;
}

class LocationUnavailableException implements Exception {
  const LocationUnavailableException(this.message);
  final String message;
}

class MobileLocationService {
  const MobileLocationService(this.api);
  final ApiClient api;

  Future<MobileLocationPreview> captureAndValidate() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      throw const LocationUnavailableException(
        'Ative a localização do aparelho para registrar o ponto.',
      );
    }
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      throw const LocationUnavailableException(
        'Autorize a localização precisa nas configurações do Android.',
      );
    }
    final position = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: Duration(seconds: 15),
      ),
    );
    final snapshot = MobileLocationSnapshot(
      latitude: position.latitude,
      longitude: position.longitude,
      accuracyMeters: position.accuracy,
      capturedAt: position.timestamp,
      isMocked: position.isMocked,
    );
    final response = await api.post(
      '/api/mobile/localizacao/validar',
      snapshot.toJson(),
    );
    final unit = Map<String, dynamic>.from(response['unidade'] as Map);
    final encodedMap = response['mapa_png_base64']?.toString();
    return MobileLocationPreview(
      snapshot: snapshot,
      distanceMeters: (response['distancia_metros'] as num).toDouble(),
      unitName: unit['nome']?.toString() ?? 'Unidade',
      radiusMeters: (unit['raio_metros'] as num).toInt(),
      address: response['endereco']?.toString(),
      mapBytes: encodedMap == null || encodedMap.isEmpty
          ? null
          : base64Decode(encodedMap),
    );
  }
}
