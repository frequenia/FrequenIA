import 'dart:convert';

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
