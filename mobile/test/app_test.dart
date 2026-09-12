import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:mobile/auth/auth_controller.dart';
import 'package:mobile/core/api_client.dart';
import 'package:mobile/core/session_store.dart';
import 'package:mobile/main.dart';
import 'package:mobile/schedule/schedule_models.dart';
import 'package:mobile/schedule/schedule_page.dart';

void main() {
  const baseUrl = 'https://api.example.test';

  setUpAll(() => initializeDateFormatting('pt_BR'));

  testWidgets('sem sessão exibe o login', (tester) async {
    final controller = AuthController(
      ApiClient(
        client: MockClient((_) async => http.Response('{}', 200)),
        sessionStore: MemorySessionStore(),
        baseUrl: baseUrl,
      ),
    );
    await controller.restoreSession();

    await tester.pumpWidget(FrequenIAApp(controller: controller));

    expect(find.text('Bem-vindo ao\nFrequenIA'), findsOneWidget);
    expect(find.text('Entrar'), findsOneWidget);
  });

  test('login salva tokens e valida o contexto em /auth/me', () async {
    final store = MemorySessionStore();
    final requests = <http.Request>[];
    final client = MockClient((request) async {
      requests.add(request);
      if (request.url.path == '/login') {
        expect(jsonDecode(request.body), {'cpf': '12345678901', 'senha': 'x'});
        return jsonResponse({
          'access_token': 'access-a',
          'refresh_token': 'refresh-a',
        });
      }
      expect(request.url.path, '/auth/me');
      expect(request.headers['Authorization'], 'Bearer access-a');
      return jsonResponse(meResponse);
    });
    final controller = AuthController(
      ApiClient(client: client, sessionStore: store, baseUrl: baseUrl),
    );

    await controller.login('12345678901', 'x');

    expect(controller.status, AuthStatus.authenticated);
    expect(controller.user, meResponse);
    expect(store.tokens?.accessToken, 'access-a');
    expect(store.tokens?.refreshToken, 'refresh-a');
    expect(requests.map((request) => request.url.path), ['/login', '/auth/me']);
  });

  test('login inválido não salva tokens', () async {
    final store = MemorySessionStore();
    final client = MockClient(
      (_) async =>
          jsonResponse({'erro': 'Credenciais inválidas.'}, statusCode: 401),
    );
    final controller = AuthController(
      ApiClient(client: client, sessionStore: store, baseUrl: baseUrl),
    );

    await expectLater(
      controller.login('00000000000', 'inválida'),
      throwsA(
        isA<ApiException>().having(
          (error) => error.statusCode,
          'statusCode',
          401,
        ),
      ),
    );

    expect(store.tokens, isNull);
    expect(controller.isAuthenticated, isFalse);
  });

  test('reinício restaura uma sessão válida com /auth/me', () async {
    final store = MemorySessionStore(
      const SessionTokens(accessToken: 'access-a', refreshToken: 'refresh-a'),
    );
    final client = MockClient((request) async {
      expect(request.url.path, '/auth/me');
      expect(request.headers['Authorization'], 'Bearer access-a');
      return jsonResponse(meResponse);
    });
    final controller = AuthController(
      ApiClient(client: client, sessionStore: store, baseUrl: baseUrl),
    );

    await controller.restoreSession();

    expect(controller.status, AuthStatus.authenticated);
    expect(controller.user, meResponse);
  });

  test('access expirado faz refresh rotativo e repete /auth/me', () async {
    final store = MemorySessionStore(
      const SessionTokens(accessToken: 'access-a', refreshToken: 'refresh-a'),
    );
    var meCalls = 0;
    var refreshCalls = 0;
    final client = MockClient((request) async {
      if (request.url.path == '/auth/refresh') {
        refreshCalls++;
        expect(jsonDecode(request.body)['refresh_token'], 'refresh-a');
        return jsonResponse({
          'access_token': 'access-b',
          'refresh_token': 'refresh-b',
        });
      }
      meCalls++;
      if (request.headers['Authorization'] == 'Bearer access-a') {
        return jsonResponse({'erro': 'Token expirado.'}, statusCode: 401);
      }
      expect(request.headers['Authorization'], 'Bearer access-b');
      return jsonResponse(meResponse);
    });
    final controller = AuthController(
      ApiClient(client: client, sessionStore: store, baseUrl: baseUrl),
    );

    await controller.restoreSession();

    expect(controller.status, AuthStatus.authenticated);
    expect(refreshCalls, 1);
    expect(meCalls, 2);
    expect(store.tokens?.accessToken, 'access-b');
    expect(store.tokens?.refreshToken, 'refresh-b');
  });

  test('refresh revogado limpa a sessão e retorna ao estado anônimo', () async {
    final store = MemorySessionStore(
      const SessionTokens(accessToken: 'expired', refreshToken: 'revoked'),
    );
    final client = MockClient((request) async {
      return jsonResponse({'erro': 'Refresh token inválido.'}, statusCode: 401);
    });
    final controller = AuthController(
      ApiClient(client: client, sessionStore: store, baseUrl: baseUrl),
    );

    await controller.restoreSession();

    expect(controller.status, AuthStatus.unauthenticated);
    expect(store.tokens, isNull);
  });

  test('requisições concorrentes compartilham um único refresh', () async {
    final store = MemorySessionStore(
      const SessionTokens(accessToken: 'access-a', refreshToken: 'refresh-a'),
    );
    var refreshCalls = 0;
    final client = MockClient((request) async {
      if (request.url.path == '/auth/me') return jsonResponse(meResponse);
      if (request.url.path == '/auth/refresh') {
        refreshCalls++;
        await Future<void>.delayed(const Duration(milliseconds: 20));
        return jsonResponse({
          'access_token': 'access-b',
          'refresh_token': 'refresh-b',
        });
      }
      if (request.headers['Authorization'] == 'Bearer access-a') {
        return jsonResponse({'erro': 'Token expirado.'}, statusCode: 401);
      }
      return jsonResponse({'ok': true});
    });
    final api = ApiClient(
      client: client,
      sessionStore: store,
      baseUrl: baseUrl,
    );
    await api.restoreSession();

    await Future.wait([api.get('/first'), api.get('/second')]);

    expect(refreshCalls, 1);
    expect(store.tokens?.accessToken, 'access-b');
    expect(store.tokens?.refreshToken, 'refresh-b');
  });

  test('403 informa falta de permissão sem apagar a sessão', () async {
    final store = MemorySessionStore(
      const SessionTokens(accessToken: 'access-a', refreshToken: 'refresh-a'),
    );
    final client = MockClient((request) async {
      if (request.url.path == '/auth/me') return jsonResponse(meResponse);
      return jsonResponse({'erro': 'Acesso negado.'}, statusCode: 403);
    });
    final api = ApiClient(
      client: client,
      sessionStore: store,
      baseUrl: baseUrl,
    );
    await api.restoreSession();

    await expectLater(
      api.post('/administracao'),
      throwsA(
        isA<ApiException>()
            .having((error) => error.statusCode, 'statusCode', 403)
            .having((error) => error.message, 'message', 'Acesso negado.'),
      ),
    );
    expect(store.tokens, isNotNull);
  });

  test('logout envia Bearer ao backend e sempre limpa tokens', () async {
    final store = MemorySessionStore(
      const SessionTokens(accessToken: 'access-a', refreshToken: 'refresh-a'),
    );
    var logoutCalled = false;
    final client = MockClient((request) async {
      if (request.url.path == '/auth/me') return jsonResponse(meResponse);
      expect(request.url.path, '/auth/logout');
      expect(request.headers['Authorization'], 'Bearer access-a');
      logoutCalled = true;
      return jsonResponse({'ok': true});
    });
    final controller = AuthController(
      ApiClient(client: client, sessionStore: store, baseUrl: baseUrl),
    );
    await controller.restoreSession();

    await controller.logout();

    expect(logoutCalled, isTrue);
    expect(store.tokens, isNull);
    expect(controller.status, AuthStatus.unauthenticated);
  });

  test('backend indisponível não causa crash nem expõe tokens', () async {
    final store = MemorySessionStore(
      const SessionTokens(accessToken: 'secret-a', refreshToken: 'secret-r'),
    );
    final client = MockClient(
      (_) async => throw http.ClientException('offline'),
    );
    final controller = AuthController(
      ApiClient(client: client, sessionStore: store, baseUrl: baseUrl),
    );

    await controller.restoreSession();

    expect(controller.status, AuthStatus.unauthenticated);
    expect(controller.sessionMessage, 'Não foi possível conectar ao servidor.');
    expect(controller.sessionMessage, isNot(contains('secret')));
    expect(store.tokens, isNotNull);
  });

  test('parse da jornada preserva múltiplos períodos na ordem correta', () {
    final response = ScheduleResponse.fromJson(scheduleResponse());

    expect(response.schedule?.shift.name, 'Administrativo');
    expect(response.schedule?.periods, hasLength(4));
    expect(response.schedule?.periods.map((period) => period.order), [
      1,
      2,
      3,
      4,
    ]);
  });

  test('parse identifica período noturno pela virada de dia', () {
    final response = ScheduleResponse.fromJson(
      scheduleResponse(
        periods: [periodResponse(1, '22:00', '02:00', endDayOffset: 1)],
      ),
    );

    expect(response.schedule?.periods.single.endsNextDay, isTrue);
  });

  test('parse aceita jornada nula', () {
    final response = ScheduleResponse.fromJson({
      'data': '2026-09-07',
      'jornada': null,
    });

    expect(response.schedule, isNull);
  });

  testWidgets('tela exibe turno, vigência e todos os períodos', (tester) async {
    final api = ApiClient(
      client: MockClient((_) async => jsonResponse(scheduleResponse())),
      sessionStore: MemorySessionStore(),
      baseUrl: baseUrl,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: SchedulePage(api: api)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Administrativo'), findsOneWidget);
    expect(find.text('01/02/2026 — atual'), findsOneWidget);
    expect(find.text('4 períodos configurados'), findsOneWidget);
    expect(find.text('08:00 – 10:00'), findsOneWidget);
    expect(find.text('10:15 – 12:00'), findsOneWidget);
    expect(find.text('13:00 – 15:00'), findsOneWidget);
    expect(find.text('15:15 – 17:00'), findsOneWidget);
  });

  testWidgets('tela apresenta virada de dia no turno noturno', (tester) async {
    final api = ApiClient(
      client: MockClient(
        (_) async => jsonResponse(
          scheduleResponse(
            periods: [periodResponse(1, '22:00', '02:00', endDayOffset: 1)],
          ),
        ),
      ),
      sessionStore: MemorySessionStore(),
      baseUrl: baseUrl,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: SchedulePage(api: api)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('22:00 – 02:00 (+1 dia)'), findsOneWidget);
  });

  testWidgets('jornada nula apresenta estado neutro', (tester) async {
    final api = ApiClient(
      client: MockClient(
        (_) async => jsonResponse({'data': '2026-09-07', 'jornada': null}),
      ),
      sessionStore: MemorySessionStore(),
      baseUrl: baseUrl,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: SchedulePage(api: api)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Nenhuma jornada definida no momento.'), findsOneWidget);
  });

  test('401 renova tokens e repete somente a consulta da jornada', () async {
    final store = MemorySessionStore(
      const SessionTokens(accessToken: 'access-a', refreshToken: 'refresh-a'),
    );
    var scheduleCalls = 0;
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
        expect(request.url.path, '/api/jornada');
        expect(request.url.queryParameters, isEmpty);
        scheduleCalls++;
        if (request.headers['Authorization'] == 'Bearer access-a') {
          return jsonResponse({'erro': 'Token expirado.'}, statusCode: 401);
        }
        expect(request.headers['Authorization'], 'Bearer access-b');
        return jsonResponse(scheduleResponse());
      }),
      sessionStore: store,
      baseUrl: baseUrl,
    );
    await api.restoreSession();

    final response = ScheduleResponse.fromJson(await api.get('/api/jornada'));

    expect(response.schedule?.shift.name, 'Administrativo');
    expect(scheduleCalls, 2);
    expect(refreshCalls, 1);
    expect(store.tokens?.refreshToken, 'refresh-b');
  });

  test(
    'refresh inválido encerra a sessão durante consulta da jornada',
    () async {
      final store = MemorySessionStore(
        const SessionTokens(accessToken: 'access-a', refreshToken: 'refresh-a'),
      );
      var expired = false;
      final api = ApiClient(
        client: MockClient((request) async {
          if (request.url.path == '/auth/me') return jsonResponse(meResponse);
          if (request.url.path == '/auth/refresh') {
            return jsonResponse({'erro': 'Sessão revogada.'}, statusCode: 401);
          }
          return jsonResponse({'erro': 'Token expirado.'}, statusCode: 401);
        }),
        sessionStore: store,
        baseUrl: baseUrl,
      )..onSessionExpired = () => expired = true;
      await api.restoreSession();

      await expectLater(
        api.get('/api/jornada'),
        throwsA(
          isA<ApiException>().having(
            (error) => error.statusCode,
            'statusCode',
            401,
          ),
        ),
      );

      expect(expired, isTrue);
      expect(store.tokens, isNull);
    },
  );

  testWidgets('403 informa acesso negado sem limpar a sessão', (tester) async {
    final store = MemorySessionStore(
      const SessionTokens(accessToken: 'access-a', refreshToken: 'refresh-a'),
    );
    final api = ApiClient(
      client: MockClient((request) async {
        if (request.url.path == '/auth/me') return jsonResponse(meResponse);
        return jsonResponse({'erro': 'Acesso negado.'}, statusCode: 403);
      }),
      sessionStore: store,
      baseUrl: baseUrl,
    );
    await api.restoreSession();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: SchedulePage(api: api)),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text('Você não tem permissão para consultar esta jornada.'),
      findsOneWidget,
    );
    expect(store.tokens, isNotNull);
  });

  testWidgets('backend indisponível mostra erro sem causar crash', (
    tester,
  ) async {
    final api = ApiClient(
      client: MockClient((_) async => throw http.ClientException('offline')),
      sessionStore: MemorySessionStore(),
      baseUrl: baseUrl,
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: SchedulePage(api: api)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Não foi possível conectar ao servidor.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

const meResponse = <String, dynamic>{
  'user_id': 'user-1',
  'funcionario_id': 'employee-1',
  'empresa_id': 'company-1',
};

Map<String, dynamic> scheduleResponse({List<Map<String, dynamic>>? periods}) =>
    {
      'data': '2026-09-07',
      'jornada': {
        'turno': {
          'id': 'shift-1',
          'nome': 'Administrativo',
          'timezone': 'America/Sao_Paulo',
          'status': 'ativo',
        },
        'vigencia': {'inicio': '2026-02-01', 'fim': null},
        'periodos':
            periods ??
            [
              periodResponse(4, '15:15', '17:00'),
              periodResponse(2, '10:15', '12:00'),
              periodResponse(1, '08:00', '10:00'),
              periodResponse(3, '13:00', '15:00'),
            ],
      },
    };

Map<String, dynamic> periodResponse(
  int order,
  String start,
  String end, {
  int endDayOffset = 0,
}) => {
  'id': 'period-$order',
  'dia_semana': 1,
  'ordem': order,
  'inicio': start,
  'fim': end,
  'fim_dia_offset': endDayOffset,
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
