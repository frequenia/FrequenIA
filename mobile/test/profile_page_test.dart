import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mobile/auth/auth_controller.dart';
import 'package:mobile/core/api_client.dart';
import 'package:mobile/profile/profile_page.dart';

void main() {
  const baseUrl = 'https://api.example.test';

  Widget screen(MockClient client) {
    final controller = AuthController(
      ApiClient(client: client, baseUrl: baseUrl),
    );
    return MaterialApp(
      home: Scaffold(body: ProfilePage(controller: controller)),
    );
  }

  http.Response response(Map<String, dynamic> body, [int status = 200]) =>
      http.Response(
        jsonEncode(body),
        status,
        headers: {'content-type': 'application/json'},
      );

  testWidgets('mostra dados reais e não apresenta UUIDs técnicos', (
    tester,
  ) async {
    final requests = <http.Request>[];
    await tester.pumpWidget(
      screen(
        MockClient((request) async {
          requests.add(request);
          return response({
            'nome': 'Ana Teste',
            'cpf_mascarado': '***.***.***-12',
            'telefone': '11999999999',
            'email': 'ana@example.invalid',
            'matricula': 'M-17',
            'perfil': 'funcionario',
            'empresa': 'Empresa A',
            'unidade': 'Piloto',
            'equipe': 'TI',
            'cargo': 'Analista',
          });
        }),
      ),
    );
    await tester.pumpAndSettle();

    expect(requests.single.url.path, '/api/perfil');
    expect(requests.single.url.queryParameters, isEmpty);
    expect(find.text('Ana Teste'), findsOneWidget);
    expect(find.text('***.***.***-12'), findsOneWidget);
    expect(find.text('Empresa A'), findsOneWidget);
    expect(find.text('Funcionário'), findsOneWidget);
    expect(find.text('user_id'), findsNothing);
    expect(find.text('funcionario_id'), findsNothing);
  });

  testWidgets('campos opcionais nulos aparecem como Não informado', (
    tester,
  ) async {
    await tester.pumpWidget(
      screen(
        MockClient(
          (_) async => response({
            'nome': 'Ana Teste',
            'cpf_mascarado': '***.***.***-12',
            'telefone': null,
            'email': null,
            'matricula': 'M-17',
            'perfil': 'funcionario',
            'empresa': 'Empresa A',
            'unidade': 'Piloto',
            'equipe': null,
            'cargo': null,
          }),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Não informado'), findsWidgets);
  });

  testWidgets('erro da API mantém estado legível e permite atualizar', (
    tester,
  ) async {
    var calls = 0;
    await tester.pumpWidget(
      screen(
        MockClient((_) async {
          calls++;
          if (calls == 1) return response({'erro': 'Sessão inválida.'}, 401);
          return response({'nome': 'Ana Teste'});
        }),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Sessão inválida.'), findsOneWidget);
    await tester.tap(find.text('Atualizar'));
    await tester.pumpAndSettle();
    expect(find.text('Ana Teste'), findsOneWidget);
    expect(calls, 2);
  });
}
