import 'dart:convert';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/core/api_client.dart';
import 'package:mobile/requests/requests_page.dart';

void main() {
  const baseUrl = 'https://api.example.test';
  http.Response json(Map<String, dynamic> value, [int status = 200]) =>
      http.Response(
        jsonEncode(value),
        status,
        headers: {'content-type': 'application/json'},
      );

  for (final rejected in [false, true]) {
    testWidgets(
      'tipo incorreto mostra envio e resultado (rejeitada=$rejected)',
      (tester) async {
        await tester.binding.setSurfaceSize(const Size(1000, 1400));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final response = Completer<http.Response>();
        final posts = <Map<String, dynamic>>[];
        final api = ApiClient(
          baseUrl: baseUrl,
          client: MockClient((request) async {
            if (request.url.path == '/api/marcacoes') {
              return json({
                'marcacoes': [
                  {
                    'id': 'synthetic-mark',
                    'tipo': 'saida',
                    'instante': '2026-11-16T15:00:00Z',
                  },
                ],
              });
            }
            if (request.method == 'POST') {
              posts.add(jsonDecode(request.body) as Map<String, dynamic>);
              return response.future;
            }
            return json({'ocorrencias': []});
          }),
        );
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(body: RequestsPage(api: api)),
          ),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.byTooltip('Nova solicitação'));
        await tester.pumpAndSettle();
        await tester.tap(find.byType(DropdownButtonFormField<String>).first);
        await tester.pumpAndSettle();
        await tester.tap(find.text('Tipo incorreto').last);
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const ValueKey('request-original-mark')));
        await tester.pumpAndSettle();
        await tester.tap(find.textContaining('Saída ·').last);
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const ValueKey('request-marking-type')));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Saída para intervalo').last);
        await tester.pumpAndSettle();
        await tester.enterText(
          find.byKey(const ValueKey('request-reason')),
          'Correção sintética de teste',
        );
        await tester.tap(find.text('Enviar solicitação'));
        await tester.pump();
        expect(find.text('Enviando…'), findsOneWidget);
        expect(posts, hasLength(1));
        expect(posts.single, {
          'tipo': 'tipo_incorreto',
          'motivo': 'Correção sintética de teste',
          'marcacao_id': 'synthetic-mark',
          'tipo_marcacao_solicitado': 'saida_intervalo',
        });
        final button = tester.widget<FilledButton>(
          find.widgetWithText(FilledButton, 'Enviando…'),
        );
        expect(button.onPressed, isNull);
        response.complete(
          rejected
              ? json({'erro': 'Correção já solicitada.'}, 409)
              : json({
                  'ocorrencia': {'id': 'synthetic-request'},
                }, 201),
        );
        await tester.pumpAndSettle();
        if (rejected) {
          expect(find.text('Correção já solicitada.'), findsOneWidget);
          expect(find.text('Enviar solicitação'), findsOneWidget);
        } else {
          expect(find.text('Nova solicitação'), findsNothing);
        }
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets('lista somente o contrato oficial de ocorrências', (
    tester,
  ) async {
    final calls = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        calls.add(request);
        return json({
          'ocorrencias': [
            {
              'id': '1',
              'tipo': 'horario_incorreto',
              'status': 'pendente_gestor',
              'motivo': 'Aplicativo indisponível',
              'criada_em': '2026-09-12T12:00:00Z',
            },
          ],
        });
      }),
      baseUrl: baseUrl,
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: RequestsPage(api: api)),
      ),
    );
    await tester.pumpAndSettle();
    expect(calls.single.url.path, '/api/ocorrencias');
    expect(find.text('Horário incorreto'), findsOneWidget);
    expect(find.text('Aplicativo indisponível'), findsOneWidget);
    expect(find.text('Pendente com gestor'), findsOneWidget);
    expect(find.text('Cancelar'), findsOneWidget);
  });

  testWidgets('cancelamento pendente usa a rota pessoal', (tester) async {
    final paths = <String>[];
    var listed = 0;
    final api = ApiClient(
      client: MockClient((request) async {
        paths.add(request.url.path);
        if (request.method == 'POST') return json({'status': 'cancelada'});
        listed++;
        return json({
          'ocorrencias': listed == 1
              ? [
                  {
                    'id': 'abc',
                    'tipo': 'justificativa',
                    'status': 'pendente_gestor',
                    'motivo': 'Trânsito',
                    'criada_em': '2026-09-12T12:00:00Z',
                  },
                ]
              : [],
        });
      }),
      baseUrl: baseUrl,
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: RequestsPage(api: api)),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancelar'));
    await tester.pumpAndSettle();
    expect(paths, [
      '/api/ocorrencias',
      '/api/ocorrencias/abc/cancelar',
      '/api/ocorrencias',
    ]);
  });

  testWidgets('erro de rede aparece sem travar', (tester) async {
    final api = ApiClient(
      client: MockClient((_) async => throw http.ClientException('offline')),
      baseUrl: baseUrl,
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: RequestsPage(api: api)),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Não foi possível conectar ao servidor.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
