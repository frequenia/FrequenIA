import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../auth/auth_controller.dart';
import '../clock/clock_page.dart';
import '../core/api_client.dart';
import '../core/theme.dart';
import '../core/widgets.dart';

class TodayPage extends StatefulWidget {
  const TodayPage({
    super.key,
    required this.controller,
    required this.cameras,
    required this.onMarked,
  });
  final AuthController controller;
  final List<CameraDescription> cameras;
  final VoidCallback onMarked;
  @override
  State<TodayPage> createState() => _TodayPageState();
}

class _TodayPageState extends State<TodayPage> {
  Map<String, dynamic>? data;
  String? failure;

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    setState(() => failure = null);
    try {
      final value = await widget.controller.api.get('/me/resumo');
      if (mounted) setState(() => data = value);
    } on ApiException catch (error) {
      if (mounted) setState(() => failure = error.message);
    }
  }

  Future<void> openClock() async {
    final marked = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => ClockPage(api: widget.controller.api)),
    );
    if (marked == true) {
      await load();
      widget.onMarked();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (data == null && failure == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (failure != null) {
      return ListView(
        padding: const EdgeInsets.all(20),
        children: [
          EmptyState(
            icon: Icons.cloud_off_rounded,
            title: 'Servidor indisponível',
            message: failure!,
            action: FilledButton(
              onPressed: load,
              child: const Text('Tentar novamente'),
            ),
          ),
        ],
      );
    }
    final marks = List<Map<String, dynamic>>.from(
      data!['marcacoes_hoje'] ?? [],
    );
    final next = data!['proxima_marcacao']?.toString();
    return RefreshIndicator(
      onRefresh: load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 30),
        children: [
          PageHeading(
            'Olá, ${data!['nome'].toString().split(' ').first}',
            subtitle: DateFormat(
              "EEEE, d 'de' MMMM",
              'pt_BR',
            ).format(DateTime.now()),
          ),
          const SizedBox(height: 22),
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [FrequenIAColors.navy, FrequenIAColors.blue],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(26),
              boxShadow: const [
                BoxShadow(
                  color: Color(0x33214560),
                  blurRadius: 26,
                  offset: Offset(0, 14),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'PRÓXIMA MARCAÇÃO',
                  style: TextStyle(
                    color: Colors.white70,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  markingLabel(next),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 27,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 20),
                FilledButton.icon(
                  onPressed: next == null ? null : openClock,
                  style: FilledButton.styleFrom(
                    backgroundColor: FrequenIAColors.cyan,
                    foregroundColor: FrequenIAColors.navy,
                  ),
                  icon: const Icon(Icons.face_retouching_natural_rounded),
                  label: Text(
                    next == null ? 'Jornada concluída' : 'Registrar ponto',
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          Text(
            'Marcações de hoje',
            style: Theme.of(context).textTheme.titleLarge
                ?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 12),
          if (marks.isEmpty)
            const EmptyState(
              icon: Icons.schedule_rounded,
              title: 'Nenhuma marcação ainda',
              message: 'Sua linha do tempo será atualizada após o primeiro registro.',
            )
          else
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(
                  children: marks.map((mark) {
                    final time = DateTime.tryParse(
                      mark['registrado_em'].toString(),
                    )?.toLocal();
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: CircleAvatar(
                        backgroundColor: FrequenIAColors.mint,
                        child: const Icon(
                          Icons.check_rounded,
                          color: FrequenIAColors.blue,
                        ),
                      ),
                      title: Text(
                        markingLabel(mark['tipo']?.toString()),
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                      subtitle: Text(statusLabel(mark['estado']?.toString())),
                      trailing: Text(
                        time == null
                            ? '--:--'
                            : DateFormat('HH:mm').format(time),
                        style: const TextStyle(
                          fontWeight: FontWeight.w800,
                          fontSize: 16,
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ),
            ),
          const SizedBox(height: 18),
          Card(
            child: ListTile(
              contentPadding: const EdgeInsets.all(18),
              leading: const Icon(Icons.info_outline_rounded),
              title: const Text(
                'Período de homologação',
                style: TextStyle(fontWeight: FontWeight.w800),
              ),
              subtitle: const Text(
                'O FrequenIA está sendo testado em paralelo e ainda não substitui o ponto oficial.',
              ),
            ),
          ),
        ],
      ),
    );
  }
}
