import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SessionTokens {
  const SessionTokens({required this.accessToken, required this.refreshToken});

  final String accessToken;
  final String refreshToken;
}

abstract interface class SessionStore {
  Future<SessionTokens?> read();
  Future<void> write(SessionTokens tokens);
  Future<void> clear();
}

class SecureSessionStore implements SessionStore {
  SecureSessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _accessKey = 'frequenia_access_token';
  static const _refreshKey = 'frequenia_refresh_token';

  final FlutterSecureStorage _storage;

  @override
  Future<SessionTokens?> read() async {
    final accessToken = await _storage.read(key: _accessKey);
    final refreshToken = await _storage.read(key: _refreshKey);
    if (accessToken == null || refreshToken == null) return null;
    return SessionTokens(accessToken: accessToken, refreshToken: refreshToken);
  }

  @override
  Future<void> write(SessionTokens tokens) async {
    // O refresh rotacionado deve ser persistido antes do access token novo.
    await _storage.write(key: _refreshKey, value: tokens.refreshToken);
    await _storage.write(key: _accessKey, value: tokens.accessToken);
  }

  @override
  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
