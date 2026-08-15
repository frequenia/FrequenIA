import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

const String apiUrl = 'http://192.168.0.108:5000';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final cameras = await availableCameras();

  runApp(FrequenciaApp(cameras: cameras));
}

class FrequenciaApp extends StatelessWidget {
  final List<CameraDescription> cameras;

  const FrequenciaApp({super.key, required this.cameras});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'FREQUEN.IA',
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
      ),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('FREQUEN.IA'), centerTitle: true),
      body: Center(
        child: ElevatedButton(
          onPressed: () {
            Navigator.push(
              context,
              MaterialPageRoute(
                builder: (context) => CameraPage(
                  cameras: context
                      .findAncestorWidgetOfExactType<FrequenciaApp>()!
                      .cameras,
                ),
              ),
            );
          },
          child: const Text('IR PARA CÂMERA'),
        ),
      ),
    );
  }
}

class CameraPage extends StatefulWidget {
  final List<CameraDescription> cameras;

  const CameraPage({super.key, required this.cameras});

  @override
  State<CameraPage> createState() => _CameraPageState();
}

class _CameraPageState extends State<CameraPage> {
  CameraController? controller;
  XFile? foto;

  @override
  void initState() {
    super.initState();
    inicializarCamera();
  }

  Future<void> inicializarCamera() async {
    if (widget.cameras.isEmpty) {
      return;
    }

    final camera = widget.cameras.firstWhere(
      (camera) => camera.lensDirection == CameraLensDirection.front,
      orElse: () => widget.cameras.first,
    );

    controller = CameraController(
      camera,
      ResolutionPreset.medium,
      enableAudio: false,
    );

    await controller!.initialize();

    if (mounted) {
      setState(() {});
    }
  }

  Future<void> tirarFoto() async {
    if (controller == null || !controller!.value.isInitialized) {
      return;
    }

    final imagem = await controller!.takePicture();

    setState(() {
      foto = imagem;
    });
  }

  void tirarNovamente() {
    setState(() {
      foto = null;
    });
  }

  Future<void> confirmarFoto() async {
    if (foto == null) {
      return;
    }

    try {
      final requisicao = http.MultipartRequest(
        'POST',
        Uri.parse('$apiUrl/mobile/foto'),
      );

      requisicao.files.add(
        await http.MultipartFile.fromPath('foto', foto!.path),
      );

      final resposta = await requisicao.send();

      if (!mounted) {
        return;
      }

      if (resposta.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Foto enviada com sucesso!')),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Erro ao enviar foto: ${resposta.statusCode}'),
          ),
        );
      }
    } catch (e) {
      if (!mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Não foi possível enviar a foto')),
      );
    }
  }

  @override
  void dispose() {
    controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (controller == null || !controller!.value.isInitialized) {
      return Scaffold(
        appBar: AppBar(title: const Text('Câmera')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Câmera'), centerTitle: true),
      body: Column(
        children: [
          Expanded(
            child: foto == null
                ? CameraPreview(controller!)
                : Image.file(File(foto!.path), fit: BoxFit.contain),
          ),

          Padding(
            padding: const EdgeInsets.all(20),
            child: foto == null
                ? ElevatedButton(
                    onPressed: tirarFoto,
                    child: const Text('TIRAR FOTO'),
                  )
                : Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      ElevatedButton(
                        onPressed: tirarNovamente,
                        child: const Text('TIRAR NOVAMENTE'),
                      ),
                      ElevatedButton(
                        onPressed: confirmarFoto,
                        child: const Text('CONFIRMAR'),
                      ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}
