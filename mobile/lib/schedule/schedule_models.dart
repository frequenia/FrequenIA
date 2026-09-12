class ScheduleResponse {
  const ScheduleResponse({required this.date, required this.schedule});

  final DateTime date;
  final WorkSchedule? schedule;

  factory ScheduleResponse.fromJson(Map<String, dynamic> json) {
    final rawDate = json['data']?.toString();
    if (rawDate == null) {
      throw const FormatException('Data da jornada ausente.');
    }

    final rawSchedule = json['jornada'];
    if (rawSchedule == null) {
      return ScheduleResponse(date: DateTime.parse(rawDate), schedule: null);
    }
    if (rawSchedule is! Map<String, dynamic>) {
      throw const FormatException('Jornada inválida.');
    }

    return ScheduleResponse(
      date: DateTime.parse(rawDate),
      schedule: WorkSchedule.fromJson(rawSchedule),
    );
  }
}

class WorkSchedule {
  WorkSchedule({
    required this.shift,
    required this.validity,
    required List<ShiftPeriod> periods,
  }) : periods = List.unmodifiable(
         [...periods]..sort((first, second) {
           final dayComparison = first.weekday.compareTo(second.weekday);
           return dayComparison != 0
               ? dayComparison
               : first.order.compareTo(second.order);
         }),
       );

  final Shift shift;
  final ScheduleValidity validity;
  final List<ShiftPeriod> periods;

  factory WorkSchedule.fromJson(Map<String, dynamic> json) {
    final rawShift = json['turno'];
    final rawValidity = json['vigencia'];
    final rawPeriods = json['periodos'];
    if (rawShift is! Map<String, dynamic> ||
        rawValidity is! Map<String, dynamic> ||
        rawPeriods is! List) {
      throw const FormatException('Dados da jornada incompletos.');
    }

    return WorkSchedule(
      shift: Shift.fromJson(rawShift),
      validity: ScheduleValidity.fromJson(rawValidity),
      periods: rawPeriods.map((item) {
        if (item is! Map<String, dynamic>) {
          throw const FormatException('Período inválido.');
        }
        return ShiftPeriod.fromJson(item);
      }).toList(),
    );
  }
}

class Shift {
  const Shift({
    required this.id,
    required this.name,
    required this.timezone,
    required this.status,
  });

  final String id;
  final String name;
  final String timezone;
  final String status;

  factory Shift.fromJson(Map<String, dynamic> json) => Shift(
    id: _requiredText(json, 'id'),
    name: _requiredText(json, 'nome'),
    timezone: _requiredText(json, 'timezone'),
    status: _requiredText(json, 'status'),
  );
}

class ScheduleValidity {
  const ScheduleValidity({required this.start, this.end});

  final DateTime start;
  final DateTime? end;

  factory ScheduleValidity.fromJson(Map<String, dynamic> json) {
    final rawEnd = json['fim']?.toString();
    return ScheduleValidity(
      start: DateTime.parse(_requiredText(json, 'inicio')),
      end: rawEnd == null || rawEnd.isEmpty ? null : DateTime.parse(rawEnd),
    );
  }
}

class ShiftPeriod {
  const ShiftPeriod({
    this.id,
    required this.weekday,
    required this.order,
    required this.start,
    required this.end,
    required this.endDayOffset,
  });

  final String? id;
  final int weekday;
  final int order;
  final String start;
  final String end;
  final int endDayOffset;

  bool get endsNextDay => endDayOffset == 1;

  factory ShiftPeriod.fromJson(Map<String, dynamic> json) => ShiftPeriod(
    id: json['id']?.toString(),
    weekday: _requiredInt(json, 'dia_semana'),
    order: _requiredInt(json, 'ordem'),
    start: _requiredText(json, 'inicio'),
    end: _requiredText(json, 'fim'),
    endDayOffset: _requiredInt(json, 'fim_dia_offset'),
  );
}

String _requiredText(Map<String, dynamic> json, String key) {
  final value = json[key]?.toString();
  if (value == null || value.isEmpty) {
    throw FormatException('Campo $key ausente.');
  }
  return value;
}

int _requiredInt(Map<String, dynamic> json, String key) {
  final value = json[key];
  if (value is int) return value;
  final parsed = int.tryParse(value?.toString() ?? '');
  if (parsed == null) throw FormatException('Campo $key inválido.');
  return parsed;
}
