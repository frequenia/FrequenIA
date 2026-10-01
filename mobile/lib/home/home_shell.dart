import 'package:flutter/material.dart';

import '../auth/auth_controller.dart';
import '../clock/clock_page.dart';
import '../history/history_page.dart';
import '../notifications/notifications_page.dart';
import '../profile/profile_page.dart';
import '../requests/requests_page.dart';
import '../schedule/schedule_page.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.controller});

  final AuthController controller;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int index = 0;

  @override
  Widget build(BuildContext context) {
    final pages = [
      _AuthenticatedHome(controller: widget.controller),
      SchedulePage(api: widget.controller.api),
      HistoryPage(api: widget.controller.api),
      RequestsPage(api: widget.controller.api, active: index == 3),
      ProfilePage(controller: widget.controller, active: index == 4),
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'FrequenIA',
          style: TextStyle(fontWeight: FontWeight.w800),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.notifications_outlined),
            tooltip: 'Notificações',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => NotificationsPage(api: widget.controller.api),
              ),
            ),
          ),
        ],
      ),
      body: IndexedStack(index: index, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Início',
          ),
          NavigationDestination(
            icon: Icon(Icons.calendar_month_outlined),
            selectedIcon: Icon(Icons.calendar_month),
            label: 'Jornada',
          ),
          NavigationDestination(
            icon: Icon(Icons.history_outlined),
            selectedIcon: Icon(Icons.history),
            label: 'Histórico',
          ),
          NavigationDestination(
            icon: Icon(Icons.assignment_outlined),
            selectedIcon: Icon(Icons.assignment),
            label: 'Solicitações',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Perfil',
          ),
        ],
      ),
    );
  }
}

class _AuthenticatedHome extends StatelessWidget {
  const _AuthenticatedHome({required this.controller});

  final AuthController controller;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(
          'Olá, ${controller.user?['nome']?.toString().split(' ').first ?? ''}',
          style: Theme.of(context).textTheme.headlineSmall
              ?.copyWith(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 8),
        Text(
          'Consulte sua jornada, registros e solicitações.',
          style: Theme.of(context).textTheme.bodyLarge,
        ),
        const SizedBox(height: 24),
        FilledButton.icon(
          onPressed: () async {
            final marked = await Navigator.push<bool>(
              context,
              MaterialPageRoute(builder: (_) => ClockPage(api: controller.api)),
            );
            if (context.mounted && marked == true) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Ponto registrado com sucesso.')),
              );
            }
          },
          icon: const Icon(Icons.face_retouching_natural_rounded),
          label: const Text('Registrar ponto facial'),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.busy ? null : controller.logout,
          icon: const Icon(Icons.logout),
          label: const Text('Sair da conta'),
        ),
      ],
    );
  }
}
