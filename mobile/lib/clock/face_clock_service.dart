import 'dart:math';

import '../core/api_client.dart';

enum ClockEventType {
  entrada('entrada', 'Entrada'),
  saidaIntervalo('saida_intervalo', 'Saída para intervalo'),
  retornoIntervalo('retorno_intervalo', 'Retorno do intervalo'),
  saida('saida', 'Saída');

  const ClockEventType(this.value, this.label);
  final String value;
  final String label;
}

class FaceClockOperation {
  const FaceClockOperation({
    required this.type,
    required this.attemptId,
    required this.idempotencyKey,
  });

  final ClockEventType type;
  final String attemptId;
  final String idempotencyKey;
}

class FaceClockResult {
  const FaceClockResult.notVerified(this.reason)
    : marking = null,
      operation = null;

  const FaceClockResult.marked(this.marking, this.operation) : reason = 'match';

  final String reason;
  final Map<String, dynamic>? marking;
  final FaceClockOperation? operation;
  bool get wasMarked => marking != null;
}

class FaceClockMarkException implements Exception {
  const FaceClockMarkException(this.error, this.operation);
  final ApiException error;
  final FaceClockOperation operation;
}

class FaceClockBusyException implements Exception {
  const FaceClockBusyException();
}

class FaceClockService {
  FaceClockService(this.api, {String Function()? idempotencyKeyFactory})
    : _idempotencyKeyFactory = idempotencyKeyFactory ?? generateUuidV4;

  final ApiClient api;
  final String Function() _idempotencyKeyFactory;
  bool _busy = false;

  Future<FaceClockResult> submit({
    String? imagePath,
    required ClockEventType type,
    FaceClockOperation? retryOperation,
  }) async {
    if (_busy) throw const FaceClockBusyException();
    _busy = true;
    try {
      var operation = retryOperation;
      if (operation == null) {
        if (imagePath == null || imagePath.isEmpty) {
          throw const ApiException('Não foi possível capturar a imagem.');
        }
        final verification = await api.postMultipart(
          '/api/biometria/verificar',
          fieldName: 'imagem',
          filePath: imagePath,
        );
        if (verification['verificado'] != true) {
          return FaceClockResult.notVerified(
            verification['motivo']?.toString() ?? 'nao_corresponde',
          );
        }
        final attemptId = verification['tentativa_facial_id']?.toString();
        if (attemptId == null || attemptId.isEmpty) {
          throw const ApiException(
            'O servidor não retornou uma verificação facial válida.',
          );
        }
        operation = FaceClockOperation(
          type: type,
          attemptId: attemptId,
          idempotencyKey: _idempotencyKeyFactory(),
        );
      }

      try {
        final response = await api.postWithHeaders(
          '/api/marcacoes/facial',
          {
            'tipo': operation.type.value,
            'tentativa_facial_id': operation.attemptId,
          },
          {'Idempotency-Key': operation.idempotencyKey},
        );
        final rawMarking = response['marcacao'];
        if (rawMarking is! Map) {
          throw const ApiException('O servidor não confirmou a marcação.');
        }
        return FaceClockResult.marked(
          Map<String, dynamic>.from(rawMarking),
          operation,
        );
      } on ApiException catch (error) {
        throw FaceClockMarkException(error, operation);
      }
    } finally {
      _busy = false;
    }
  }
}

String generateUuidV4() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  final hex = bytes
      .map((value) => value.toRadixString(16).padLeft(2, '0'))
      .join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
      '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}
