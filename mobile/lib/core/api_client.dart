import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
// Disponibilizado transitivamente por package:http; o hotfix nao adiciona pacotes.
// ignore: depend_on_referenced_packages
import 'package:http_parser/http_parser.dart';

import 'api_config.dart';
import 'session_store.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.code, this.statusCode, this.details});

  final String message;
  final String? code;
  final int? statusCode;
  final dynamic details;

  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({
    http.Client? client,
    SessionStore? sessionStore,
    String? baseUrl,
    this.timeout = const Duration(seconds: 15),
  }) : _client = client ?? http.Client(),
       _sessionStore = sessionStore ?? SecureSessionStore(),
       _baseUrl = _normalizeBaseUrl(baseUrl ?? ApiConfig.baseUrl);

  final http.Client _client;
  final SessionStore _sessionStore;
  final String _baseUrl;
  final Duration timeout;
  static const Duration _multipartTimeout = Duration(minutes: 5);

  String? _accessToken;
  String? _refreshToken;
  Future<void>? _refreshInFlight;

  void Function()? onSessionExpired;

  Future<Map<String, dynamic>?> restoreSession() async {
    final tokens = await _sessionStore.read();
    if (tokens == null) return null;
    _accessToken = tokens.accessToken;
    _refreshToken = tokens.refreshToken;

    try {
      return await getMe();
    } on ApiException catch (error) {
      if (error.isUnauthorized) await clearSession(notify: false);
      rethrow;
    }
  }

  Future<Map<String, dynamic>> login(String cpf, String password) async {
    final response = await _sendJson(
      'POST',
      '/login',
      body: {'cpf': cpf, 'senha': password},
    );
    final data = _decode(response);
    await _saveTokens(data, requireRefresh: true);
    return getMe();
  }

  Future<Map<String, dynamic>> getMe() => get('/auth/me');

  Future<void> logout() async {
    try {
      if (_accessToken != null) {
        await _request('POST', '/auth/logout', retryOnUnauthorized: true);
      }
    } catch (_) {
      // A limpeza local é obrigatória mesmo quando o servidor está indisponível.
    } finally {
      await clearSession(notify: false);
    }
  }

  Future<void> clearSession({bool notify = true}) async {
    _accessToken = null;
    _refreshToken = null;
    await _sessionStore.clear();
    if (notify) onSessionExpired?.call();
  }

  Future<Map<String, dynamic>> get(String path, {Map<String, String>? query}) =>
      _request('GET', path, query: query, retryOnUnauthorized: true);

  Future<Map<String, dynamic>> post(
    String path, [
    Map<String, dynamic>? body,
  ]) => _request('POST', path, body: body, retryOnUnauthorized: true);

  Future<Map<String, dynamic>> postWithHeaders(
    String path,
    Map<String, dynamic> body,
    Map<String, String> headers,
  ) => _request(
    'POST',
    path,
    body: body,
    headers: headers,
    retryOnUnauthorized: true,
  );

  Future<Map<String, dynamic>> postMultipart(
    String path, {
    required String fieldName,
    required String filePath,
  }) async {
    var response = await _sendMultipart(
      path,
      fieldName: fieldName,
      filePath: filePath,
      accessToken: _accessToken,
    );
    if (response.statusCode == 401 && _refreshToken != null) {
      await refreshSession();
      response = await _sendMultipart(
        path,
        fieldName: fieldName,
        filePath: filePath,
        accessToken: _accessToken,
      );
    }
    return _decode(response);
  }

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? query,
    Map<String, String>? headers,
    bool retryOnUnauthorized = false,
  }) async {
    var response = await _sendJson(
      method,
      path,
      body: body,
      query: query,
      accessToken: _accessToken,
      headers: headers,
    );

    if (response.statusCode == 401 &&
        retryOnUnauthorized &&
        _refreshToken != null) {
      await refreshSession();
      response = await _sendJson(
        method,
        path,
        body: body,
        query: query,
        accessToken: _accessToken,
        headers: headers,
      );
    }

    return _decode(response);
  }

  Future<void> refreshSession() {
    final activeRefresh = _refreshInFlight;
    if (activeRefresh != null) return activeRefresh;

    late final Future<void> trackedRefresh;
    trackedRefresh = _performRefresh().whenComplete(() {
      if (identical(_refreshInFlight, trackedRefresh)) {
        _refreshInFlight = null;
      }
    });
    _refreshInFlight = trackedRefresh;
    return trackedRefresh;
  }

  Future<void> _performRefresh() async {
    final refreshToken = _refreshToken;
    if (refreshToken == null) {
      await clearSession();
      throw const ApiException(
        'Sua sessão expirou. Entre novamente.',
        statusCode: 401,
      );
    }

    try {
      final response = await _sendJson(
        'POST',
        '/auth/refresh',
        body: {'refresh_token': refreshToken},
      );
      final data = _decode(response);
      await _saveTokens(data, requireRefresh: true);
    } on ApiException catch (error) {
      if (error.isUnauthorized) await clearSession();
      rethrow;
    }
  }

  Future<http.Response> _sendJson(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? query,
    String? accessToken,
    Map<String, String>? headers,
  }) async {
    final uri = Uri.parse('$_baseUrl$path').replace(queryParameters: query);
    final request = http.Request(method, uri)
      ..headers['Accept'] = 'application/json'
      ..headers['Content-Type'] = 'application/json';
    if (headers != null) request.headers.addAll(headers);
    if (accessToken != null) {
      request.headers['Authorization'] = 'Bearer $accessToken';
    }
    if (body != null) request.body = jsonEncode(body);

    try {
      final streamed = await _client.send(request).timeout(timeout);
      return await http.Response.fromStream(streamed).timeout(timeout);
    } on TimeoutException {
      throw const ApiException(
        'O servidor demorou para responder. Tente novamente.',
      );
    } on http.ClientException {
      throw const ApiException('Não foi possível conectar ao servidor.');
    }
  }

  Future<http.Response> _sendMultipart(
    String path, {
    required String fieldName,
    required String filePath,
    String? accessToken,
  }) async {
    final request = http.MultipartRequest('POST', Uri.parse('$_baseUrl$path'))
      ..headers['Accept'] = 'application/json';
    if (accessToken != null) {
      request.headers['Authorization'] = 'Bearer $accessToken';
    }
    request.files.add(
      await http.MultipartFile.fromPath(
        fieldName,
        filePath,
        contentType: MediaType('image', 'jpeg'),
      ),
    );

    try {
      final streamed = await _client.send(request).timeout(_multipartTimeout);
      return await http.Response.fromStream(
        streamed,
      ).timeout(_multipartTimeout);
    } on TimeoutException {
      throw const ApiException(
        'O servidor demorou para responder. Tente novamente.',
      );
    } on http.ClientException {
      throw const ApiException('Não foi possível conectar ao servidor.');
    }
  }

  Map<String, dynamic> _decode(http.Response response) {
    Map<String, dynamic> data = const {};
    if (response.body.isNotEmpty) {
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) data = decoded;
      } on FormatException {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          throw const ApiException(
            'O servidor retornou uma resposta inválida.',
          );
        }
      }
    }

    if (response.statusCode >= 200 && response.statusCode < 300) return data;

    final backendMessage =
        data['erro']?.toString() ?? data['mensagem']?.toString();
    throw ApiException(
      backendMessage ?? _messageForStatus(response.statusCode),
      code: (data['codigo'] ?? data['motivo'])?.toString(),
      statusCode: response.statusCode,
      details: data['detalhes'],
    );
  }

  Future<void> _saveTokens(
    Map<String, dynamic> data, {
    required bool requireRefresh,
  }) async {
    final accessToken = data['access_token']?.toString();
    final refreshToken = data['refresh_token']?.toString();
    if (accessToken == null ||
        accessToken.isEmpty ||
        (requireRefresh && (refreshToken == null || refreshToken.isEmpty))) {
      throw const ApiException('O servidor não retornou uma sessão válida.');
    }

    _accessToken = accessToken;
    _refreshToken = refreshToken ?? _refreshToken;
    await _sessionStore.write(
      SessionTokens(accessToken: _accessToken!, refreshToken: _refreshToken!),
    );
  }

  static String _normalizeBaseUrl(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      throw ArgumentError('BASE_URL não pode ser vazia.');
    }
    return trimmed.endsWith('/')
        ? trimmed.substring(0, trimmed.length - 1)
        : trimmed;
  }

  static String _messageForStatus(int statusCode) => switch (statusCode) {
    400 => 'Verifique os dados informados.',
    401 => 'Sua sessão expirou. Entre novamente.',
    403 => 'Você não tem permissão para realizar esta ação.',
    404 => 'O recurso solicitado não foi encontrado.',
    409 => 'Não foi possível concluir devido a um conflito.',
    >= 500 => 'O servidor encontrou um problema. Tente novamente.',
    _ => 'Não foi possível concluir a operação.',
  };
}
