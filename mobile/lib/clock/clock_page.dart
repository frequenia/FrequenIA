import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/api_client.dart';
import '../core/theme.dart';
import '../core/widgets.dart';
import 'face_clock_service.dart';
import 'mobile_location_service.dart';

class ClockPage extends StatefulWidget {
  const ClockPage({super.key, required this.api});
  final ApiClient api;
  @override
  State<ClockPage> createState() => _ClockPageState();
}

class _ClockPageState extends State<ClockPage> {
  CameraController? camera;
  late final FaceClockService service;
  late final MobileLocationService locationService;
  bool busy = false;
  String instruction = 'Posicione seu rosto dentro da moldura';
  String? failure;
  ClockEventType selectedType = ClockEventType.entrada;
  FaceClockOperation? pendingOperation;

  @override
  void initState() {
    super.initState();
    service = FaceClockService(widget.api);
    locationService = MobileLocationService(widget.api);
    initialize();
  }

  Future<void> initialize() async {
    setState(() => failure = null);
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        if (mounted) {
          setState(
            () => failure = 'Nenhuma câmera foi encontrada neste aparelho.',
          );
        }
        return;
      }
      final selected = cameras.firstWhere(
        (item) => item.lensDirection == CameraLensDirection.front,
        orElse: () => cameras.first,
      );
      final controller = CameraController(
        selected,
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await controller.initialize();
      if (!mounted) return;
      setState(() => camera = controller);
    } on CameraException catch (error) {
      if (mounted) {
        setState(
          () => failure = error.code.contains('AccessDenied')
              ? 'A permissão da câmera foi negada. Autorize-a nas configurações do Android.'
              : 'Não foi possível iniciar a câmera deste aparelho.',
        );
      }
    } catch (_) {
      if (mounted) {
        setState(() => failure = 'Não foi possível iniciar a câmera.');
      }
    }
  }

  Future<void> start() async {
    if (camera == null || busy) return;
    setState(() {
      busy = true;
      failure = null;
      instruction = 'Capturando e verificando...';
    });
    XFile? captured;
    try {
      setState(() => instruction = 'Validando sua localização...');
      final location = await locationService.captureAndValidate();
      if (!mounted || !await confirmLocation(location)) {
        if (mounted) {
          setState(() {
            instruction = 'Posicione seu rosto dentro da moldura';
            busy = false;
          });
        }
        return;
      }
      setState(() => instruction = 'Capturando e verificando...');
      captured = await camera!.takePicture();
      final result = await service.submit(
        imagePath: captured.path,
        type: selectedType,
        location: location.snapshot,
      );
      if (!mounted) return;
      if (!result.wasMarked) {
        setState(() {
          failure = _verificationMessage(result.reason);
          instruction = 'Posicione seu rosto e tente novamente';
          busy = false;
        });
        return;
      }
      pendingOperation = null;
      await showReceipt(result.marking!);
      if (mounted) Navigator.pop(context, true);
    } on FaceClockMarkException catch (exception) {
      if (mounted) {
        final retryable =
            exception.error.statusCode == null ||
            (exception.error.statusCode ?? 0) >= 500;
        setState(() {
          pendingOperation = retryable ? exception.operation : null;
          failure = _apiMessage(exception.error);
          instruction = retryable
              ? 'Sua face foi validada. Tente concluir a marcação.'
              : 'Posicione seu rosto e tente novamente';
          busy = false;
        });
      }
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          failure = _apiMessage(error);
          instruction = 'Vamos tentar novamente?';
          busy = false;
        });
      }
    } on LocationUnavailableException catch (error) {
      if (mounted) {
        setState(() {
          failure = error.message;
          instruction = 'Localização necessária para registrar o ponto';
          busy = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          failure = 'A conexão foi interrompida. Nenhuma imagem foi guardada.';
          busy = false;
        });
      }
    } finally {
      final path = captured?.path;
      if (path != null) {
        try {
          final file = File(path);
          if (await file.exists()) await file.delete();
        } catch (_) {
          // O arquivo temporário não é mantido nem reutilizado pelo aplicativo.
        }
      }
    }
  }

  Future<void> retryMarking() async {
    final operation = pendingOperation;
    if (operation == null || busy) return;
    setState(() {
      busy = true;
      failure = null;
      instruction = 'Concluindo sua marcação...';
    });
    try {
      final result = await service.submit(
        type: operation.type,
        retryOperation: operation,
      );
      if (!mounted) return;
      pendingOperation = null;
      await showReceipt(result.marking!);
      if (mounted) Navigator.pop(context, true);
    } on FaceClockMarkException catch (exception) {
      if (mounted) {
        final retryable =
            exception.error.statusCode == null ||
            (exception.error.statusCode ?? 0) >= 500;
        setState(() {
          pendingOperation = retryable ? exception.operation : null;
          failure = _apiMessage(exception.error);
          busy = false;
        });
      }
    }
  }

  String _verificationMessage(String reason) => switch (reason) {
    'liveness_reprovado' => 'Não foi possível confirmar que a imagem é uma captura ao vivo. Tente novamente.',
    'biometria_ausente' =>
      'Você não possui biometria ativa. Procure o responsável pelo cadastro.',
    _ => 'Rosto não reconhecido. Tente novamente em boa iluminação.',
  };

  String _apiMessage(ApiException error) {
    final status = error.statusCode;
    if (status != null && status >= 500) {
      return status == 503
          ? 'A verificação facial está temporariamente indisponível.'
          : 'O servidor não conseguiu concluir a operação. Tente novamente.';
    }
    return switch (status) {
      403 when error.code == 'fora_do_perimetro' =>
        'Você está fora do perímetro permitido para sua unidade.',
      403 when error.code == 'localizacao_simulada' =>
        'Uma localização simulada foi detectada. A marcação foi bloqueada.',
      403 when error.code == 'marcacao_mobile_desabilitada' => 'A marcação pelo celular não está habilitada para sua unidade. Use o quiosque.',
      409 when error.code == 'localizacao_expirada' =>
        'A localização expirou. Reinicie a marcação.',
      422 when error.code == 'localizacao_imprecisa' => 'O sinal de GPS está impreciso. Vá para uma área aberta e tente novamente.',
      403 => 'Você não tem permissão para registrar este ponto.',
      409 when error.code == 'tentativa_facial_expirada' =>
        'A verificação facial expirou. Faça uma nova captura.',
      409 when error.code == 'tentativa_facial_utilizada' =>
        'Esta verificação já foi utilizada.',
      409 when error.code == 'marcacao_recente' =>
        'Já existe uma marcação registrada recentemente.',
      409 when error.code == 'biometria_ausente' =>
        'Você não possui biometria ativa. Procure o responsável pelo cadastro.',
      409 => 'Não foi possível registrar o ponto devido a um conflito.',
      422 => 'Mantenha somente um rosto visível e tente novamente.',
      _ => error.message,
    };
  }

  Future<bool> confirmLocation(MobileLocationPreview preview) async {
    final result = await showModalBottomSheet<bool>(
      context: context,
      isDismissible: false,
      enableDrag: false,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (preview.mapBytes != null)
                ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: Image.memory(
                    preview.mapBytes!,
                    height: 180,
                    width: double.infinity,
                    fit: BoxFit.cover,
                  ),
                )
              else
                const Icon(Icons.location_on, size: 52),
              const SizedBox(height: 14),
              Text(
                preview.unitName,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              if (preview.address != null)
                Text(preview.address!, textAlign: TextAlign.center),
              const SizedBox(height: 8),
              Text(
                '${preview.distanceMeters.toStringAsFixed(0)} m da unidade • '
                'precisão ${preview.snapshot.accuracyMeters.toStringAsFixed(0)} m • '
                'raio ${preview.radiusMeters} m',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 18),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('Cancelar'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('Continuar'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
    return result == true;
  }

  Future<void> showReceipt(Map<String, dynamic> mark) =>
      showModalBottomSheet<void>(
        context: context,
        isDismissible: false,
        enableDrag: false,
        showDragHandle: false,
        builder: (context) {
          final timestamp = DateTime.tryParse(mark['instante'].toString())
              ?.toLocal();
          return SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 72,
                    height: 72,
                    decoration: const BoxDecoration(
                      color: FrequenIAColors.mint,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      Icons.check_rounded,
                      size: 42,
                      color: FrequenIAColors.blue,
                    ),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    'Ponto registrado',
                    style: Theme.of(context).textTheme.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    markingLabel(mark['tipo']?.toString()),
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 18),
                  Text(
                    timestamp == null
                        ? ''
                        : DateFormat("dd/MM/yyyy 'às' HH:mm:ss")
                              .format(timestamp),
                    style: const TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 6),
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Concluir'),
                  ),
                ],
              ),
            ),
          );
        },
      );

  @override
  void dispose() {
    camera?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF06141E),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.white,
        title: const Text('Registrar ponto'),
      ),
      body: failure != null && camera == null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: EmptyState(
                  icon: Icons.no_photography_outlined,
                  title: 'Câmera indisponível',
                  message: failure!,
                ),
              ),
            )
          : camera == null
          ? const Center(child: CircularProgressIndicator(color: Colors.white))
          : Stack(
              children: [
                Positioned.fill(child: CameraPreview(camera!)),
                Positioned.fill(
                  child: IgnorePointer(
                    child: CustomPaint(painter: FaceOverlayPainter()),
                  ),
                ),
                Positioned(
                  left: 20,
                  right: 20,
                  bottom: 28,
                  child: SafeArea(
                    child: Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: const Color(0xE60B273F),
                        borderRadius: BorderRadius.circular(24),
                      ),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            instruction,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          DropdownButtonFormField<ClockEventType>(
                            initialValue: selectedType,
                            dropdownColor: const Color(0xFF0B273F),
                            style: const TextStyle(color: Colors.white),
                            decoration: const InputDecoration(
                              labelText: 'Tipo de marcação',
                              labelStyle: TextStyle(color: Colors.white70),
                            ),
                            items: ClockEventType.values
                                .map(
                                  (type) => DropdownMenuItem(
                                    value: type,
                                    child: Text(type.label),
                                  ),
                                )
                                .toList(),
                            onChanged: busy
                                ? null
                                : (value) {
                                    if (value != null) {
                                      setState(() => selectedType = value);
                                    }
                                  },
                          ),
                          if (busy) ...[
                            const SizedBox(height: 14),
                            const LinearProgressIndicator(
                              backgroundColor: Colors.white24,
                              color: FrequenIAColors.cyan,
                            ),
                          ],
                          if (failure != null) ...[
                            const SizedBox(height: 10),
                            Text(
                              failure!,
                              textAlign: TextAlign.center,
                              style: const TextStyle(color: Color(0xFFFFC8C8)),
                            ),
                          ],
                          const SizedBox(height: 16),
                          FilledButton.icon(
                            onPressed: busy
                                ? null
                                : pendingOperation == null
                                ? start
                                : retryMarking,
                            style: FilledButton.styleFrom(
                              backgroundColor: FrequenIAColors.cyan,
                              foregroundColor: FrequenIAColors.navy,
                            ),
                            icon: const Icon(
                              Icons.face_retouching_natural_rounded,
                            ),
                            label: Text(
                              pendingOperation != null
                                  ? 'Concluir marcação'
                                  : failure == null
                                  ? 'Iniciar verificação'
                                  : 'Tentar novamente',
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}

class FaceOverlayPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final overlay = Paint()..color = Colors.black.withValues(alpha: .46);
    final hole = Rect.fromCenter(
      center: Offset(size.width / 2, size.height * .38),
      width: size.width * .68,
      height: size.height * .48,
    );
    final path = Path()..fillType = PathFillType.evenOdd;
    path.addRect(Offset.zero & size);
    path.addOval(hole);
    canvas.drawPath(path, overlay..blendMode = BlendMode.srcOver);
    canvas.drawOval(
      hole,
      Paint()
        ..color = FrequenIAColors.cyan
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
