import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/api_client.dart';
import '../core/widgets.dart';

class HistoryPage extends StatefulWidget {
  const HistoryPage({super.key, required this.api});
  final ApiClient api;
  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage> {
  List<Map<String, dynamic>> marks = [];
  bool loading = true;
  String? failure;

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    setState(() {
      loading = true;
      failure = null;
    });
    try {
      final result = await widget.api.get('/marcacoes');
      if (mounted) {
        setState(
          () => marks = List<Map<String, dynamic>>.from(
            result['marcacoes'] ?? [],
          ),
        );
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => failure = error.message);
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: load,
    child: ListView(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 30),
      children: [
        const PageHeading(
          'Histórico',
          subtitle: 'Consulte seus registros mais recentes',
        ),
        const SizedBox(height: 22),
        if (loading)
          const Center(
            child: Padding(
              padding: EdgeInsets.all(48),
              child: CircularProgressIndicator(),
            ),
          )
        else if (failure != null)
          EmptyState(
            icon: Icons.cloud_off,
            title: 'Não foi possível carregar',
            message: failure!,
            action: FilledButton(
              onPressed: load,
              child: const Text('Tentar novamente'),
            ),
          )
        else if (marks.isEmpty)
          const EmptyState(
            icon: Icons.history_rounded,
            title: 'Histórico vazio',
            message: 'As marcações concluídas aparecerão aqui.',
          )
        else
          ...marks.map((mark) {
            final timestamp = DateTime.tryParse(
              mark['registrado_em'].toString(),
            )?.toLocal();
            return Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Card(
                child: ListTile(
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 18,
                    vertical: 10,
                  ),
                  leading: Icon(
                    Icons.fingerprint_rounded,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  title: Text(
                    markingLabel(mark['tipo']?.toString()),
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  subtitle: Text(
                    timestamp == null
                        ? ''
                        : DateFormat("dd/MM/yyyy · HH:mm").format(timestamp),
                  ),
                  trailing: StatusPill(mark['estado']?.toString() ?? ''),
                ),
              ),
            );
          }),
      ],
    ),
  );
}
