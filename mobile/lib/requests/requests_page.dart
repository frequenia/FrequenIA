import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/api_client.dart';
import '../core/widgets.dart';

class RequestsPage extends StatefulWidget {
  const RequestsPage({super.key, required this.api, this.active = true});
  final ApiClient api;
  final bool active;
  @override
  State<RequestsPage> createState() => _RequestsPageState();
}

class _RequestsPageState extends State<RequestsPage> {
  static const int _maxAttachmentBytes = 10 * 1024 * 1024;
  List<Map<String, dynamic>> rows = [];
  bool loading = false;
  String? failure;

  @override
  void initState() {
    super.initState();
    if (widget.active) load();
  }

  @override
  void didUpdateWidget(covariant RequestsPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.active && !oldWidget.active && rows.isEmpty && !loading) load();
  }

  Future<void> load() async {
    if (loading) return;
    setState(() {
      loading = true;
      failure = null;
    });
    try {
      final result = await widget.api.get('/api/ocorrencias');
      if (mounted) {
        setState(
          () => rows = List<Map<String, dynamic>>.from(
            result['ocorrencias'] ?? [],
          ),
        );
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => failure = error.message);
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  String _withOffset(DateTime value) {
    final local = value.toLocal(), offset = value.toLocal().timeZoneOffset;
    final sign = offset.isNegative ? '-' : '+';
    String two(int number) => number.toString().padLeft(2, '0');
    return '${DateFormat("yyyy-MM-dd'T'HH:mm:ss").format(local)}$sign${two(offset.abs().inHours)}:${two(offset.abs().inMinutes.remainder(60))}';
  }

  Future<PlatformFile?> _pickAttachment() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['pdf', 'jpg', 'jpeg', 'png'],
      allowMultiple: false,
      withData: false,
    );
    final file = result?.files.single;
    if (file == null) return null;
    if (file.path == null || file.path!.isEmpty) {
      throw const ApiException(
        'Não foi possível acessar o arquivo selecionado.',
      );
    }
    if (file.size == 0) {
      throw const ApiException('O comprovante está vazio.');
    }
    if (file.size > _maxAttachmentBytes) {
      throw const ApiException('O comprovante deve ter no máximo 10 MiB.');
    }
    return file;
  }

  String _attachmentMime(String name) {
    final extension = name.toLowerCase().split('.').last;
    return extension == 'pdf'
        ? 'application/pdf'
        : extension == 'png'
        ? 'image/png'
        : 'image/jpeg';
  }

  Future<void> replaceAttachment(String correctionId) async {
    try {
      final file = await _pickAttachment();
      if (file == null) return;
      await widget.api.postMultipart(
        '/api/ocorrencias/$correctionId/comprovante',
        fieldName: 'comprovante',
        filePath: file.path!,
        method: 'PUT',
        mimeType: _attachmentMime(file.name),
      );
      await load();
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  Future<void> removeAttachment(String correctionId) async {
    try {
      await widget.api.delete('/api/ocorrencias/$correctionId/comprovante');
      await load();
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  Future<void> createRequest() async {
    List<Map<String, dynamic>> markings = [];
    try {
      final result = await widget.api.get('/api/marcacoes');
      markings = List<Map<String, dynamic>>.from(result['marcacoes'] ?? []);
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.message)));
      }
      return;
    }
    if (!mounted) return;
    final key = GlobalKey<FormState>();
    final reason = TextEditingController(),
        requestedTime = TextEditingController(text: '08:00');
    String category = 'esquecimento_marcacao', markingType = 'entrada';
    String? markingId;
    PlatformFile? attachment;
    DateTime day = DateTime.now();
    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => Padding(
          padding: EdgeInsets.fromLTRB(
            22,
            8,
            22,
            MediaQuery.viewInsetsOf(context).bottom + 24,
          ),
          child: Form(
            key: key,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Nova solicitação',
                    style: Theme.of(context).textTheme.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    initialValue: category,
                    decoration: const InputDecoration(labelText: 'Categoria'),
                    items:
                        const {
                              'esquecimento_marcacao':
                                  'Esquecimento de marcação',
                              'horario_incorreto': 'Horário incorreto',
                              'tipo_incorreto': 'Tipo incorreto',
                              'justificativa': 'Justificativa',
                              'outro': 'Outro',
                            }.entries
                            .map(
                              (e) => DropdownMenuItem(
                                value: e.key,
                                child: Text(e.value),
                              ),
                            )
                            .toList(),
                    onChanged: (value) => update(() => category = value!),
                  ),
                  if (category == 'horario_incorreto' ||
                      category == 'tipo_incorreto') ...[
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      decoration: const InputDecoration(
                        labelText: 'Marcação original',
                      ),
                      items: markings
                          .map(
                            (item) => DropdownMenuItem(
                              value: item['id'].toString(),
                              child: Text(
                                '${_labelMarking(item['tipo'])} · ${_dateLabel(item['instante'])}',
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: (value) => markingId = value,
                      validator: (value) => value == null
                          ? 'Selecione a marcação original'
                          : null,
                    ),
                  ],
                  if (category == 'esquecimento_marcacao' ||
                      category == 'horario_incorreto') ...[
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
                        if (selected != null) update(() => day = selected);
                      },
                      icon: const Icon(Icons.calendar_today),
                      label: Text(DateFormat('dd/MM/yyyy').format(day)),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: requestedTime,
                      decoration: const InputDecoration(
                        labelText: 'Horário (HH:mm)',
                      ),
                      validator: (value) =>
                          RegExp(r'^(?:[01]\d|2[0-3]):[0-5]\d$')
                              .hasMatch(value ?? '')
                          ? null
                          : 'Informe HH:mm',
                    ),
                  ],
                  if (category == 'esquecimento_marcacao' ||
                      category == 'tipo_incorreto') ...[
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: markingType,
                      decoration: const InputDecoration(
                        labelText: 'Tipo da marcação',
                      ),
                      items:
                          const {
                                'entrada': 'Entrada',
                                'saida_intervalo': 'Saída para intervalo',
                                'retorno_intervalo': 'Retorno do intervalo',
                                'saida': 'Saída',
                              }.entries
                              .map(
                                (e) => DropdownMenuItem(
                                  value: e.key,
                                  child: Text(e.value),
                                ),
                              )
                              .toList(),
                      onChanged: (value) => markingType = value!,
                    ),
                  ],
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: reason,
                    minLines: 3,
                    maxLines: 5,
                    decoration: const InputDecoration(labelText: 'Motivo'),
                    validator: (value) => (value ?? '').trim().isEmpty
                        ? 'Informe o motivo'
                        : null,
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: () async {
                      try {
                        final selected = await _pickAttachment();
                        if (selected != null) {
                          update(() => attachment = selected);
                        }
                      } on ApiException catch (error) {
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text(error.message)),
                          );
                        }
                      }
                    },
                    icon: const Icon(Icons.attach_file),
                    label: Text(
                      attachment == null
                          ? 'Adicionar comprovante opcional'
                          : attachment!.name,
                    ),
                  ),
                  const Text(
                    'PDF, JPEG ou PNG, com no máximo 10 MiB.',
                    textAlign: TextAlign.center,
                  ),
                  if (attachment != null)
                    TextButton(
                      onPressed: () => update(() => attachment = null),
                      child: const Text('Remover arquivo selecionado'),
                    ),
                  const SizedBox(height: 18),
                  FilledButton(
                    onPressed: () async {
                      if (!key.currentState!.validate()) return;
                      final body = <String, dynamic>{
                        'tipo': category,
                        'motivo': reason.text.trim(),
                      };
                      if (category == 'esquecimento_marcacao') {
                        final parts = requestedTime.text.split(':');
                        body['instante_solicitado'] = _withOffset(
                          DateTime(
                            day.year,
                            day.month,
                            day.day,
                            int.parse(parts[0]),
                            int.parse(parts[1]),
                          ),
                        );
                        body['tipo_marcacao_solicitado'] = markingType;
                      } else if (category == 'horario_incorreto') {
                        final parts = requestedTime.text.split(':');
                        body['marcacao_id'] = markingId;
                        body['instante_solicitado'] = _withOffset(
                          DateTime(
                            day.year,
                            day.month,
                            day.day,
                            int.parse(parts[0]),
                            int.parse(parts[1]),
                          ),
                        );
                      } else if (category == 'tipo_incorreto') {
                        body['marcacao_id'] = markingId;
                        body['tipo_marcacao_solicitado'] = markingType;
                      }
                      try {
                        if (attachment == null) {
                          await widget.api.post('/api/ocorrencias', body);
                        } else {
                          await widget.api.postMultipart(
                            '/api/ocorrencias',
                            fieldName: 'comprovante',
                            filePath: attachment!.path!,
                            fields: body.map(
                              (key, value) => MapEntry(key, value.toString()),
                            ),
                            mimeType: _attachmentMime(attachment!.name),
                          );
                        }
                        if (context.mounted) {
                          Navigator.pop(context, true);
                        }
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
    reason.dispose();
    requestedTime.dispose();
    if (created == true) load();
  }

  Future<void> cancel(String id) async {
    try {
      await widget.api.post('/api/ocorrencias/$id/cancelar');
      await load();
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: load,
    child: ListView(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 30),
      children: [
        PageHeading(
          'Solicitações',
          subtitle: 'Acompanhe suas correções de ponto',
          trailing: IconButton.filled(
            onPressed: loading ? null : createRequest,
            tooltip: 'Nova solicitação',
            icon: const Icon(Icons.add),
          ),
        ),
        const SizedBox(height: 18),
        if (loading && rows.isEmpty)
          const Center(child: CircularProgressIndicator())
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
        else if (rows.isEmpty)
          const EmptyState(
            icon: Icons.assignment_outlined,
            title: 'Nenhuma solicitação',
            message: 'Suas solicitações de correção aparecerão aqui.',
          )
        else
          ...rows.map(
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
                              _label(item['tipo']),
                              style: const TextStyle(
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                          StatusPill(item['status']?.toString() ?? ''),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(item['motivo']?.toString() ?? 'Não informado'),
                      const SizedBox(height: 8),
                      Text(
                        _dateLabel(item['criada_em']),
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      const SizedBox(height: 8),
                      if (item['comprovante'] case final Map attachment)
                        Text(
                          '${attachment['nome']} · ${attachment['tipo_mime']} · ${_sizeLabel(attachment['tamanho_bytes'])} · ${_attachmentSecurityLabel(attachment)}',
                          style: Theme.of(context).textTheme.bodySmall,
                        )
                      else
                        Text(
                          'Sem comprovante',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      if (item['status'] == 'pendente_gestor')
                        Wrap(
                          alignment: WrapAlignment.end,
                          children: [
                            TextButton.icon(
                              onPressed: () =>
                                  replaceAttachment(item['id'].toString()),
                              icon: const Icon(Icons.attach_file),
                              label: Text(
                                item['comprovante'] == null
                                    ? 'Adicionar comprovante'
                                    : 'Substituir comprovante',
                              ),
                            ),
                            if (item['comprovante'] != null)
                              TextButton(
                                onPressed: () =>
                                    removeAttachment(item['id'].toString()),
                                child: const Text('Remover comprovante'),
                              ),
                            TextButton(
                              onPressed: () => cancel(item['id'].toString()),
                              child: const Text('Cancelar'),
                            ),
                          ],
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ),
      ],
    ),
  );
}

String _label(dynamic value) =>
    const {
      'esquecimento_marcacao': 'Esquecimento de marcação',
      'horario_incorreto': 'Horário incorreto',
      'tipo_incorreto': 'Tipo incorreto',
      'justificativa': 'Justificativa',
      'outro': 'Outro',
    }[value] ??
    value?.toString() ??
    'Ocorrência';
String _labelMarking(dynamic value) =>
    const {
      'entrada': 'Entrada',
      'saida_intervalo': 'Saída para intervalo',
      'retorno_intervalo': 'Retorno do intervalo',
      'saida': 'Saída',
    }[value] ??
    value?.toString() ??
    'Marcação';
String _dateLabel(dynamic value) {
  final parsed = DateTime.tryParse(value?.toString() ?? '');
  return parsed == null
      ? 'Data não informada'
      : DateFormat('dd/MM/yyyy HH:mm').format(parsed.toLocal());
}

String _sizeLabel(dynamic value) {
  final bytes = int.tryParse(value?.toString() ?? '') ?? 0;
  return '${(bytes / 1024).toStringAsFixed(1)} KiB';
}

String _attachmentSecurityLabel(Map attachment) =>
    const {
      'analisando': 'Analisando',
      'disponivel': 'Disponível',
      'bloqueado': 'Bloqueado',
      'falha_temporaria': 'Falha temporária',
    }[attachment['situacao']] ??
    'Bloqueado';
