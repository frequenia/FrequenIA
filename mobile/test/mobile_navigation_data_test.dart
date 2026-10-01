import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/auth/auth_controller.dart';
import 'package:mobile/core/api_client.dart';
import 'package:mobile/core/session_store.dart';
import 'package:mobile/history/history_page.dart';
import 'package:mobile/home/home_shell.dart';
import 'package:mobile/notifications/notifications_page.dart';

void main() {
  const baseUrl = 'https://api.example.test';

  testWidgets('histórico usa /api/marcacoes e o campo instante', (
    tester,
  ) async {
    late Uri requested;
    final api = _api((request) async {
      requested = request.url;
      return _json({
        'marcacoes': [
          {
            'id': 'mark-1',
            'tipo': 'entrada',
            'estado': 'confirmada',
            'instante': '2026-09-24T12:34:00-03:00',
          },
        ],
      });
    });

    await tester.pumpWidget(MaterialApp(home: HistoryPage(api: api)));
    await tester.pumpAndSettle();

    expect(requested.path, '/api/marcacoes');
    expect(find.text('Entrada'), findsOneWidget);
    expect(find.textContaining('24/09/2026'), findsOneWidget);
  });

  testWidgets('histórico trata resposta vazia', (tester) async {
    final api = _api((_) async => _json({'marcacoes': []}));
    await tester.pumpWidget(MaterialApp(home: HistoryPage(api: api)));
    await tester.pumpAndSettle();
    expect(find.text('Histórico vazio'), findsOneWidget);
  });

  testWidgets('histórico trata erro HTTP', (tester) async {
    final api = _api(
      (_) async => _json({'erro': 'Falha controlada.'}, statusCode: 500),
    );
    await tester.pumpWidget(MaterialApp(home: HistoryPage(api: api)));
    await tester.pumpAndSettle();
    expect(find.text('Não foi possível carregar'), findsOneWidget);
    expect(find.text('Falha controlada.'), findsOneWidget);
  });

  testWidgets('notificações usam API oficial e marcam a própria como lida', (
    tester,
  ) async {
    final paths = <String>[];
    var read = false;
    final api = _api((request) async {
      paths.add(request.url.path);
      if (request.method == 'POST') {
        expect(request.url.path, '/api/notificacoes/notice-1/ler');
        read = true;
        return _json({
          'id': 'notice-1',
          'read_at': '2026-09-24T13:00:00-03:00',
        });
      }
      expect(request.url.path, '/api/notificacoes');
      return _json({
        'notificacoes': [
          {
            'id': 'notice-1',
            'tipo': 'ocorrencia',
            'titulo': 'Solicitação analisada',
            'mensagem': 'Sua solicitação foi analisada.',
            'created_at': '2026-09-24T12:00:00-03:00',
            'read_at': read ? '2026-09-24T13:00:00-03:00' : null,
          },
        ],
      });
    });

    await tester.pumpWidget(MaterialApp(home: NotificationsPage(api: api)));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Solicitação analisada'));
    await tester.pumpAndSettle();

    expect(paths.first, '/api/notificacoes');
    expect(paths, contains('/api/notificacoes/notice-1/ler'));
    expect(paths.where((path) => path == '/api/notificacoes'), hasLength(2));
  });

  testWidgets('notificações tratam resposta vazia', (tester) async {
    final api = _api((_) async => _json({'notificacoes': []}));
    await tester.pumpWidget(MaterialApp(home: NotificationsPage(api: api)));
    await tester.pumpAndSettle();
    expect(find.text('Tudo em dia'), findsOneWidget);
  });

  testWidgets('notificações tratam erro HTTP', (tester) async {
    final api = _api(
      (_) async => _json({'erro': 'Falha controlada.'}, statusCode: 500),
    );
    await tester.pumpWidget(MaterialApp(home: NotificationsPage(api: api)));
    await tester.pumpAndSettle();
    expect(find.text('Não foi possível carregar'), findsOneWidget);
    expect(find.text('Falha controlada.'), findsOneWidget);
  });

  testWidgets('shell navega para Histórico e Notificações sem resumo órfão', (
    tester,
  ) async {
    final paths = <String>[];
    final store = MemorySessionStore(
      const SessionTokens(accessToken: 'access', refreshToken: 'refresh'),
    );
    final api = ApiClient(
      client: MockClient((request) async {
        paths.add(request.url.path);
        return switch (request.url.path) {
          '/auth/me' => _json({'nome': 'Pessoa Piloto'}),
          '/api/jornada' => _json({'data': '2026-09-24', 'jornada': null}),
          '/api/marcacoes' => _json({'marcacoes': []}),
          '/api/notificacoes' => _json({'notificacoes': []}),
          _ => _json({'erro': 'Rota inesperada.'}, statusCode: 404),
        };
      }),
      sessionStore: store,
      baseUrl: baseUrl,
    );
    final controller = AuthController(api);
    await controller.restoreSession();

    await tester.pumpWidget(
      MaterialApp(home: HomeShell(controller: controller)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.history_outlined));
    await tester.pumpAndSettle();
    expect(find.text('Histórico vazio'), findsOneWidget);

    await tester.tap(find.byTooltip('Notificações'));
    await tester.pumpAndSettle();
    expect(find.text('Tudo em dia'), findsOneWidget);
    expect(paths, isNot(contains('/me/resumo')));
  });
}

ApiClient _api(Future<http.Response> Function(http.Request) handler) =>
    ApiClient(
      client: MockClient(handler),
      sessionStore: MemorySessionStore(),
      baseUrl: 'https://api.example.test',
    );

http.Response _json(Map<String, dynamic> body, {int statusCode = 200}) =>
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
