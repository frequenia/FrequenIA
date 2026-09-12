import 'package:flutter/material.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'auth/auth_controller.dart';
import 'auth/login_page.dart';
import 'core/api_client.dart';
import 'core/theme.dart';
import 'home/home_shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('pt_BR');
  final controller = AuthController(ApiClient());
  runApp(FrequenIAApp(controller: controller));
  await controller.restoreSession();
}

class FrequenIAApp extends StatelessWidget {
  const FrequenIAApp({super.key, required this.controller});

  final AuthController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => MaterialApp(
        title: 'FrequenIA',
        debugShowCheckedModeBanner: false,
        theme: FrequenIATheme.light,
        darkTheme: FrequenIATheme.dark,
        themeMode: ThemeMode.system,
        home: switch (controller.status) {
          AuthStatus.initializing => const _InitializingPage(),
          AuthStatus.unauthenticated => LoginPage(controller: controller),
          AuthStatus.authenticated => HomeShell(controller: controller),
        },
      ),
    );
  }
}

class _InitializingPage extends StatelessWidget {
  const _InitializingPage();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Semantics(
          label: 'Validando sessão',
          child: const CircularProgressIndicator(),
        ),
      ),
    );
  }
}
