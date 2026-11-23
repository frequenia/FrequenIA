import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/api_client.dart';
import 'package:mobile/core/session_store.dart';

class MemoryStore implements SessionStore {
  SessionTokens? tokens;
  @override
  Future<SessionTokens?> read() async => tokens;
  @override
  Future<void> write(SessionTokens value) async {
    tokens = value;
  }

  @override
  Future<void> clear() async {
    tokens = null;
  }
}

void main() {
  late Directory temporary;
  late File cached;
  setUp(() async {
    temporary = await Directory.systemTemp.createTemp(
      'frequenia-attachment-test-',
    );
    cached = await File('${temporary.path}/provider-cache-without-extension')
        .writeAsBytes([255, 216, 255, 217]);
  });
  tearDown(() async {
    await temporary.delete(recursive: true);
  });

  for (final method in ['POST', 'PUT']) {
    test(
      'comprovante $method preserva nome JPG mesmo com cache sem extensão e refresh',
      () async {
        var uploads = 0;
        final store = MemoryStore()
          ..tokens = const SessionTokens(
            accessToken: 'expired-synthetic',
            refreshToken: 'refresh-synthetic',
          );
        final api = ApiClient(
          baseUrl: 'https://api.example.test',
          sessionStore: store,
          client: MockClient((request) async {
            if (request.method == 'GET') return http.Response('{}', 200);
            if (request.url.path.contains('refresh')) {
              return http.Response(
                jsonEncode({
                  'access_token': 'new-synthetic',
                  'refresh_token': 'rotated-synthetic',
                }),
                200,
              );
            }
            uploads++;
            expect(request.method, method);
            final body = latin1.decode(request.bodyBytes);
            expect(body, contains('filename="comprovante.JPG"'));
            expect(body, isNot(contains('provider-cache-without-extension')));
            expect(body.toLowerCase(), contains('content-type: image/jpeg'));
            expect(body, contains('name="comprovante"'));
            return http.Response('{}', uploads == 1 ? 401 : 200);
          }),
        );
        await api.restoreSession();
        await api.postMultipart(
          '/api/ocorrencias',
          fieldName: 'comprovante',
          filePath: cached.path,
          fileName: 'comprovante.JPG',
          mimeType: 'image/jpeg',
          method: method,
        );
        expect(uploads, 2);
      },
    );
  }
  test('arquivo temporário removido apresenta erro legível', () async {
    final api = ApiClient(
      baseUrl: 'https://api.example.test',
      client: MockClient((_) async => throw StateError('não deve enviar')),
    );
    await expectLater(
      api.postMultipart(
        '/api/ocorrencias',
        fieldName: 'comprovante',
        filePath: '${temporary.path}/missing',
        fileName: 'foto.jpg',
      ),
      throwsA(
        isA<ApiException>().having(
          (e) => e.message,
          'mensagem',
          contains('Selecione o arquivo novamente'),
        ),
      ),
    );
  });
}
