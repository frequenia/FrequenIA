import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/api_client.dart';
import '../core/widgets.dart';

class NotificationsPage extends StatefulWidget {
  const NotificationsPage({super.key, required this.api});
  final ApiClient api;
  @override
  State<NotificationsPage> createState() => _NotificationsPageState();
}

class _NotificationsPageState extends State<NotificationsPage> {
  List<Map<String, dynamic>> rows = [];
  bool loading = true;
  String? failure;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    try {
      final result = await widget.api.get('/notificacoes');
      if (mounted) {
        setState(() {
          rows = List<Map<String, dynamic>>.from(result['notificacoes'] ?? []);
          loading = false;
        });
      }
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          failure = error.message;
          loading = false;
        });
      }
    }
  }

  Future<void> markRead(Map<String, dynamic> item) async {
    if (item['lida_em'] != null) return;
    await widget.api.post('/notificacoes/${item['id']}/ler');
    load();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Notificações')),
    body: loading
        ? const Center(child: CircularProgressIndicator())
        : failure != null
        ? Padding(
            padding: const EdgeInsets.all(20),
            child: EmptyState(
              icon: Icons.cloud_off,
              title: 'Não foi possível carregar',
              message: failure!,
            ),
          )
        : rows.isEmpty
        ? const Padding(
            padding: EdgeInsets.all(20),
            child: EmptyState(
              icon: Icons.notifications_none,
              title: 'Tudo em dia',
              message: 'Novidades sobre suas solicitações aparecerão aqui.',
            ),
          )
        : ListView.separated(
            padding: const EdgeInsets.all(20),
            itemCount: rows.length,
            separatorBuilder: (_, _) => const SizedBox(height: 10),
            itemBuilder: (context, index) {
              final item = rows[index];
              final date = DateTime.tryParse(item['criada_em'].toString())
                  ?.toLocal();
              return Card(
                child: ListTile(
                  onTap: () => markRead(item),
                  contentPadding: const EdgeInsets.all(16),
                  leading: CircleAvatar(
                    child: Icon(
                      item['lida_em'] == null
                          ? Icons.notifications_active_outlined
                          : Icons.notifications_none,
                    ),
                  ),
                  title: Text(
                    item['titulo'].toString(),
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  subtitle: Text(
                    '${item['mensagem']}\n${date == null ? '' : DateFormat('dd/MM · HH:mm').format(date)}',
                  ),
                  isThreeLine: true,
                ),
              );
            },
          ),
  );
}
