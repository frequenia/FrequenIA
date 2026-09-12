import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/api_client.dart';
import '../core/widgets.dart';

class RequestsPage extends StatefulWidget {
  const RequestsPage({super.key, required this.api});
  final ApiClient api;
  @override
  State<RequestsPage> createState() => _RequestsPageState();
}

class _RequestsPageState extends State<RequestsPage>
    with SingleTickerProviderStateMixin {
  late final TabController tabs;
  List<Map<String, dynamic>> requests = [];
  List<Map<String, dynamic>> occurrences = [];
  bool loading = true;
  String? failure;

  @override
  void initState() {
    super.initState();
    tabs = TabController(length: 2, vsync: this);
    load();
  }

  @override
  void dispose() {
    tabs.dispose();
    super.dispose();
  }

  Future<void> load() async {
    setState(() {
      loading = true;
      failure = null;
    });
    try {
      final values = await Future.wait([
        widget.api.get('/solicitacoes'),
        widget.api.get('/ocorrencias'),
      ]);
      if (mounted) {
        setState(() {
          requests = List<Map<String, dynamic>>.from(
            values[0]['solicitacoes'] ?? [],
          );
          occurrences = List<Map<String, dynamic>>.from(
            values[1]['ocorrencias'] ?? [],
          );
        });
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => failure = error.message);
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> createRequest() async {
    final formKey = GlobalKey<FormState>();
    final description = TextEditingController();
    final requestedTime = TextEditingController();
    String reason = 'esquecimento';
    DateTime day = DateTime.now();
    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setSheetState) => Padding(
          padding: EdgeInsets.fromLTRB(
            22,
            8,
            22,
            MediaQuery.viewInsetsOf(context).bottom + 24,
          ),
          child: Form(
            key: formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Solicitar correção',
                    style: Theme.of(context).textTheme.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 18),
                  DropdownButtonFormField<String>(
                    initialValue: reason,
                    decoration: const InputDecoration(labelText: 'Motivo'),
                    items:
                        const {
                              'esquecimento': 'Esquecimento',
                              'reconhecimento': 'Reconhecimento facial',
                              'internet': 'Internet',
                              'horario_incorreto': 'Horário incorreto',
                              'outro': 'Outro',
                            }.entries
                            .map(
                              (item) => DropdownMenuItem(
                                value: item.key,
                                child: Text(item.value),
                              ),
                            )
                            .toList(),
                    onChanged: (value) => reason = value!,
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: () async {
                      final selected = await showDatePicker(
                        context: context,
                        firstDate: DateTime.now().subtract(
                          const Duration(days: 90),
                        ),
                        lastDate: DateTime.now(),
                        initialDate: day,
                      );
                      if (selected != null) setSheetState(() => day = selected);
                    },
                    icon: const Icon(Icons.calendar_today_outlined),
                    label: Text(DateFormat('dd/MM/yyyy').format(day)),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: requestedTime,
                    keyboardType: TextInputType.datetime,
                    decoration: const InputDecoration(
                      labelText: 'Horário desejado (opcional)',
                      hintText: '08:00',
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: description,
                    minLines: 3,
                    maxLines: 5,
                    decoration: const InputDecoration(
                      labelText: 'Conte o que aconteceu',
                    ),
                    validator: (value) => (value ?? '').trim().length < 5
                        ? 'Descreva a situação'
                        : null,
                  ),
                  const SizedBox(height: 18),
                  FilledButton(
                    onPressed: () async {
                      if (!formKey.currentState!.validate()) return;
                      String? timestamp;
                      final parts = requestedTime.text.split(':');
                      if (parts.length == 2) {
                        timestamp = DateTime(
                          day.year,
                          day.month,
                          day.day,
                          int.tryParse(parts[0]) ?? 0,
                          int.tryParse(parts[1]) ?? 0,
                        ).toIso8601String();
                      }
                      try {
                        await widget.api.post('/solicitacoes', {
                          'data_referencia': DateFormat('yyyy-MM-dd')
                              .format(day),
                          'motivo': reason,
                          'descricao': description.text.trim(),
                          'horario_solicitado': timestamp,
                        });
                        if (context.mounted) Navigator.pop(context, true);
                      } on ApiException catch (error) {
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text(error.message)),
                          );
                        }
                      }
                    },
                    child: const Text('Enviar solicitação'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    if (created == true) load();
  }

  Widget listFor(List<Map<String, dynamic>> rows, bool correction) {
    if (rows.isEmpty) {
      return EmptyState(
        icon: correction
            ? Icons.assignment_outlined
            : Icons.fact_check_outlined,
        title: correction ? 'Nenhuma solicitação' : 'Nenhuma ocorrência',
        message: correction
            ? 'Quando precisar, solicite uma correção pelo botão abaixo.'
            : 'Ocorrências que precisem de análise aparecerão aqui.',
      );
    }
    return Column(
      children: rows
          .map(
            (item) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              correction
                                  ? item['motivo'].toString().replaceAll(
                                      '_',
                                      ' ',
                                    )
                                  : item['tipo'].toString().replaceAll(
                                      '_',
                                      ' ',
                                    ),
                              style: const TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 16,
                              ),
                            ),
                          ),
                          StatusPill(item['estado']?.toString() ?? ''),
                        ],
                      ),
                      const SizedBox(height: 10),
                      Text(item['descricao']?.toString() ?? 'Em análise'),
                      const SizedBox(height: 10),
                      Text(
                        item['criada_em']?.toString().substring(0, 10) ?? '',
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          )
          .toList(),
    );
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        PageHeading(
          'Solicitações',
          subtitle: 'Acompanhe correções e ocorrências',
          trailing: IconButton.filled(
            onPressed: createRequest,
            tooltip: 'Nova correção',
            icon: const Icon(Icons.add),
          ),
        ),
        const SizedBox(height: 16),
        TabBar(
          controller: tabs,
          tabs: const [
            Tab(text: 'Correções'),
            Tab(text: 'Ocorrências'),
          ],
        ),
        const SizedBox(height: 16),
        Expanded(
          child: loading
              ? const Center(child: CircularProgressIndicator())
              : failure != null
              ? EmptyState(
                  icon: Icons.cloud_off,
                  title: 'Não foi possível carregar',
                  message: failure!,
                  action: FilledButton(
                    onPressed: load,
                    child: const Text('Tentar novamente'),
                  ),
                )
              : TabBarView(
                  controller: tabs,
                  children: [
                    RefreshIndicator(
                      onRefresh: load,
                      child: ListView(
                        children: [
                          listFor(requests, true),
                          const SizedBox(height: 24),
                        ],
                      ),
                    ),
                    RefreshIndicator(
                      onRefresh: load,
                      child: ListView(
                        children: [
                          listFor(occurrences, false),
                          const SizedBox(height: 24),
                        ],
                      ),
                    ),
                  ],
                ),
        ),
      ],
    ),
  );
}
