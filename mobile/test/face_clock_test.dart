import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/clock/face_clock_service.dart';
import 'package:mobile/core/api_client.dart';
import 'package:mobile/core/session_store.dart';

void main() {
  const baseUrl = 'https://api.example.test';
  late Directory temporaryDirectory;
  late File image;

  setUp(() async {
    temporaryDirectory = await Directory.systemTemp.createTemp(
      'frequenia-face-',
    );
    image = await File('${temporaryDirectory.path}/capture.jpg')
        .writeAsBytes([0xff, 0xd8, 0xff, 0xd9]);
  });

  tearDown(() async {
    if (await temporaryDirectory.exists()) {
      await temporaryDirectory.delete(recursive: true);
    }
  });

  test(
    'match envia multipart e cria marcação facial com idempotência',
    () async {
      final requests = <http.Request>[];
      final api = await authenticatedApi((request) async {
        requests.add(request);
        if (request.url.path == '/api/biometria/verificar') {
          expect(
            request.headers['content-type'],
            startsWith('multipart/form-data'),
          );
          final multipartBody = latin1.decode(request.bodyBytes);
          expect(multipartBody, contains('name="imagem"'));
          expect(multipartBody, isNot(contains('funcionario_id')));
          expect(multipartBody, isNot(contains('empresa_id')));
          return jsonResponse({
            'verificado': true,
            'motivo': 'match',
            'tentativa_facial_id': 'attempt-1',
          });
        }
        expect(request.url.path, '/api/marcacoes/facial');
        expect(jsonDecode(request.body), {
          'tipo': 'entrada',
          'tentativa_facial_id': 'attempt-1',
        });
        expect(request.headers['Idempotency-Key'], 'operation-1');
        return jsonResponse({
          'marcacao': {
            'id': 'mark-1',
            'tipo': 'entrada',
            'origem': 'facial',
            'estado': 'confirmada',
            'instante': '2026-09-11T12:00:00-03:00',
          },
        }, statusCode: 201);
      });
      final service = FaceClockService(
        api,
        idempotencyKeyFactory: () => 'operation-1',
      );

      final result = await service.submit(
        imagePath: image.path,
        type: ClockEventType.entrada,
      );

      expect(result.wasMarked, isTrue);
      expect(result.marking?['id'], 'mark-1');
      expect(requests.map((request) => request.url.path), [
        '/api/biometria/verificar',
        '/api/marcacoes/facial',
      ]);
    },
  );

  for (final reason in [
    'nao_corresponde',
    'liveness_reprovado',
    'biometria_ausente',
  ]) {
    test('$reason não chama a marcação', () async {
      var markingCalls = 0;
      final api = await authenticatedApi((request) async {
        if (request.url.path == '/api/marcacoes/facial') markingCalls++;
        return jsonResponse({'verificado': false, 'motivo': reason});
      });
      final service = FaceClockService(api);

      final result = await service.submit(
        imagePath: image.path,
        type: ClockEventType.saida,
      );

      expect(result.wasMarked, isFalse);
      expect(result.reason, reason);
      expect(markingCalls, 0);
    });
  }

  test('retry da marcação reutiliza tentativa e Idempotency-Key', () async {
    var verificationCalls = 0;
    final idempotencyKeys = <String?>[];
    var markingCalls = 0;
    final api = await authenticatedApi((request) async {
      if (request.url.path == '/api/biometria/verificar') {
        verificationCalls++;
        return jsonResponse({
          'verificado': true,
          'motivo': 'match',
          'tentativa_facial_id': 'attempt-retry',
        });
      }
      markingCalls++;
      idempotencyKeys.add(request.headers['Idempotency-Key']);
      if (markingCalls == 1) {
        return jsonResponse({
          'erro': 'Temporariamente indisponível.',
        }, statusCode: 503);
      }
      return jsonResponse({
        'marcacao': {'id': 'mark-retry'},
      });
    });
    final service = FaceClockService(
      api,
      idempotencyKeyFactory: () => 'same-operation-key',
    );

    FaceClockOperation? pending;
    try {
      await service.submit(
        imagePath: image.path,
        type: ClockEventType.retornoIntervalo,
      );
      fail('A primeira marcação deveria falhar.');
    } on FaceClockMarkException catch (error) {
      pending = error.operation;
    }
    final result = await service.submit(
      type: ClockEventType.retornoIntervalo,
      retryOperation: pending,
    );

    expect(result.wasMarked, isTrue);
    expect(verificationCalls, 1);
    expect(idempotencyKeys, ['same-operation-key', 'same-operation-key']);
  });

  test('duplo envio é bloqueado enquanto a operação está ativa', () async {
    final api = await authenticatedApi((request) async {
      await Future<void>.delayed(const Duration(milliseconds: 30));
      return jsonResponse({'verificado': false, 'motivo': 'nao_corresponde'});
    });
    final service = FaceClockService(api);

    final first = service.submit(
      imagePath: image.path,
      type: ClockEventType.entrada,
    );
    await expectLater(
      service.submit(imagePath: image.path, type: ClockEventType.entrada),
      throwsA(isA<FaceClockBusyException>()),
    );
    await first;
  });

  test(
    '401 no multipart usa refresh existente e repete a verificação',
    () async {
      final store = MemorySessionStore(
        const SessionTokens(accessToken: 'access-a', refreshToken: 'refresh-a'),
      );
      var verificationCalls = 0;
      var refreshCalls = 0;
      final api = ApiClient(
        client: MockClient((request) async {
          if (request.url.path == '/auth/me') return jsonResponse(meResponse);
          if (request.url.path == '/auth/refresh') {
            refreshCalls++;
            return jsonResponse({
              'access_token': 'access-b',
              'refresh_token': 'refresh-b',
            });
          }
          verificationCalls++;
          if (request.headers['Authorization'] == 'Bearer access-a') {
            return jsonResponse({'erro': 'Token expirado.'}, statusCode: 401);
          }
          expect(request.headers['Authorization'], 'Bearer access-b');
          return jsonResponse({
            'verificado': false,
            'motivo': 'nao_corresponde',
          });
        }),
        sessionStore: store,
        baseUrl: baseUrl,
      );
      await api.restoreSession();

      await FaceClockService(api)
          .submit(imagePath: image.path, type: ClockEventType.entrada);

      expect(verificationCalls, 2);
      expect(refreshCalls, 1);
      expect(store.tokens?.refreshToken, 'refresh-b');
    },
  );

  test('409 preserva motivo biometria_ausente sem criar marcação', () async {
    final api = await authenticatedApi((request) async {
      return jsonResponse({
        'verificado': false,
        'motivo': 'biometria_ausente',
      }, statusCode: 409);
    });

    await expectLater(
      FaceClockService(api)
          .submit(imagePath: image.path, type: ClockEventType.entrada),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'status', 409)
            .having((error) => error.code, 'motivo', 'biometria_ausente'),
      ),
    );
  });

  test('UUID gerado segue versão 4', () {
    expect(
      generateUuidV4(),
      matches(
        RegExp(
          r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        ),
      ),
    );
  });
}

Future<ApiClient> authenticatedApi(
  Future<http.Response> Function(http.Request request) handler,
) async {
  final api = ApiClient(
    client: MockClient((request) async {
      if (request.url.path == '/auth/me') return jsonResponse(meResponse);
      return handler(request);
    }),
    sessionStore: MemorySessionStore(
      const SessionTokens(accessToken: 'access-a', refreshToken: 'refresh-a'),
    ),
    baseUrl: 'https://api.example.test',
  );
  await api.restoreSession();
  return api;
}

const meResponse = <String, dynamic>{
  'user_id': 'user-1',
  'funcionario_id': 'employee-1',
  'empresa_id': 'company-1',
};

http.Response jsonResponse(Map<String, dynamic> body, {int statusCode = 200}) =>
    http.Response(
      jsonEncode(body),
      statusCode,
      headers: {'content-type': 'application/json'},
    );

class MemorySessionStore implements SessionStore {
  MemorySessionStore([this.tokens]);
  SessionTokens? tokens;

  @override
  Future<void> clear() async => tokens = null;

  @override
  Future<SessionTokens?> read() async => tokens;

  @override
  Future<void> write(SessionTokens value) async => tokens = value;
}
