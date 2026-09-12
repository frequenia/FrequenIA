import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/api_client.dart';
import '../core/widgets.dart';
import 'schedule_models.dart';

class SchedulePage extends StatefulWidget {
  const SchedulePage({super.key, required this.api});

  final ApiClient api;

  @override
  State<SchedulePage> createState() => _SchedulePageState();
}

class _SchedulePageState extends State<SchedulePage> {
  ScheduleResponse? response;
  bool loading = false;
  String? failure;

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    if (loading) return;
    setState(() {
      loading = true;
      failure = null;
    });
    try {
      final result = await widget.api.get('/api/jornada');
      final parsed = ScheduleResponse.fromJson(result);
      if (mounted) setState(() => response = parsed);
    } on ApiException catch (error) {
      if (mounted) setState(() => failure = _messageFor(error));
    } on FormatException {
      if (mounted) {
        setState(() => failure = 'O servidor retornou uma jornada inválida.');
      }
    } catch (_) {
      if (mounted) {
        setState(() => failure = 'Não foi possível carregar sua jornada.');
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  String _messageFor(ApiException error) {
    if (error.statusCode == 403) {
      return 'Você não tem permissão para consultar esta jornada.';
    }
    if (error.statusCode == 404) {
      return 'A jornada solicitada não foi encontrada.';
    }
    if (error.statusCode != null && error.statusCode! >= 500) {
      return 'Não foi possível carregar sua jornada. Tente novamente.';
    }
    return error.message;
  }

  @override
  Widget build(BuildContext context) {
    if (loading && response == null) {
      return Center(
        child: Semantics(
          label: 'Carregando jornada',
          child: const CircularProgressIndicator(),
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 30),
        children: [
          PageHeading(
            'Jornada',
            subtitle: 'Consulte seu turno e seus períodos de trabalho',
            trailing: IconButton.filledTonal(
              onPressed: loading ? null : load,
              tooltip: 'Atualizar jornada',
              icon: loading
                  ? const SizedBox.square(
                      dimension: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh_rounded),
            ),
          ),
          const SizedBox(height: 22),
          if (failure != null)
            EmptyState(
              icon: Icons.cloud_off_rounded,
              title: 'Não foi possível carregar',
              message: failure!,
              action: FilledButton(
                onPressed: loading ? null : load,
                child: const Text('Tentar novamente'),
              ),
            )
          else if (response?.schedule == null)
            const EmptyState(
              icon: Icons.event_busy_outlined,
              title: 'Nenhuma jornada definida',
              message: 'Nenhuma jornada definida no momento.',
            )
          else
            _ScheduleContent(schedule: response!.schedule!),
        ],
      ),
    );
  }
}

class _ScheduleContent extends StatelessWidget {
  const _ScheduleContent({required this.schedule});

  final WorkSchedule schedule;

  @override
  Widget build(BuildContext context) {
    final dateFormat = DateFormat('dd/MM/yyyy', 'pt_BR');
    final validity = schedule.validity;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.calendar_month_rounded,
                      color: Theme.of(context).colorScheme.primary,
                      size: 32,
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            schedule.shift.name,
                            style: Theme.of(context).textTheme.titleLarge
                                ?.copyWith(fontWeight: FontWeight.w800),
                          ),
                          const SizedBox(height: 4),
                          Text(schedule.shift.timezone),
                        ],
                      ),
                    ),
                    StatusPill(schedule.shift.status),
                  ],
                ),
                const SizedBox(height: 20),
                const Divider(height: 1),
                const SizedBox(height: 16),
                Text(
                  'Vigência',
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  validity.end == null
                      ? '${dateFormat.format(validity.start)} — atual'
                      : '${dateFormat.format(validity.start)} — ${dateFormat.format(validity.end!)}',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
        Text(
          'Períodos',
          style: Theme.of(context).textTheme.titleLarge
              ?.copyWith(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 6),
        Text(
          '${schedule.periods.length} ${schedule.periods.length == 1 ? 'período configurado' : 'períodos configurados'}',
          style: TextStyle(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 12),
        if (schedule.periods.isEmpty)
          const EmptyState(
            icon: Icons.schedule_outlined,
            title: 'Sem períodos',
            message: 'Este turno ainda não possui períodos configurados.',
          )
        else
          ...schedule.periods.map(
            (period) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Card(
                child: ListTile(
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 18,
                    vertical: 10,
                  ),
                  leading: CircleAvatar(child: Text(period.order.toString())),
                  title: Text(
                    '${period.start} – ${period.end}${period.endsNextDay ? ' (+1 dia)' : ''}',
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  subtitle: Text(_weekdayLabel(period.weekday)),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

String _weekdayLabel(int value) => switch (value) {
  0 => 'Domingo',
  1 => 'Segunda-feira',
  2 => 'Terça-feira',
  3 => 'Quarta-feira',
  4 => 'Quinta-feira',
  5 => 'Sexta-feira',
  6 => 'Sábado',
  _ => 'Dia não informado',
};
