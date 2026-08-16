import 'dart:io';
import 'dart:convert';

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
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ElevatedButton(
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

            const SizedBox(height: 20),

            ElevatedButton(
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const CadastroFacialPage(),
                  ),
                );
              },
              child: const Text('CADASTRAR FACE'),
            ),

            const SizedBox(height: 20),

            ElevatedButton(
              onPressed: () {
                final app = context
                    .findAncestorWidgetOfExactType<FrequenciaApp>()!;

                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) =>
                        ReconhecimentoPage(cameras: app.cameras),
                  ),
                );
              },
              child: const Text('RECONHECER FACE'),
            ),
          ],
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

class CadastroFacialPage extends StatefulWidget {
  const CadastroFacialPage({super.key});

  @override
  State<CadastroFacialPage> createState() => _CadastroFacialPageState();
}

class _CadastroFacialPageState extends State<CadastroFacialPage> {
  List<dynamic> usuarios = [];
  bool carregando = true;

  @override
  void initState() {
    super.initState();
    carregarUsuarios();
  }

  Future<void> carregarUsuarios() async {
    try {
      final resposta = await http.get(
        Uri.parse('$apiUrl/mobile/usuarios-sem-fotos'),
      );

      if (!mounted) {
        return;
      }

      if (resposta.statusCode == 200) {
        final dados = jsonDecode(resposta.body);

        setState(() {
          usuarios = dados['usuarios'];
          carregando = false;
        });
      } else {
        setState(() {
          carregando = false;
        });
      }
    } catch (e) {
      if (!mounted) {
        return;
      }

      setState(() {
        carregando = false;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Não foi possível carregar os usuários')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Cadastro Facial'), centerTitle: true),
      body: carregando
          ? const Center(child: CircularProgressIndicator())
          : ListView.builder(
              itemCount: usuarios.length,
              itemBuilder: (context, index) {
                final usuario = usuarios[index];

                return ListTile(
                  title: Text(usuario['nome']),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () {
                    final app = context
                        .findAncestorWidgetOfExactType<FrequenciaApp>()!;

                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (context) => CadastroCameraPage(
                          cameras: app.cameras,
                          usuarioId: usuario['id'],
                          nomeUsuario: usuario['nome'],
                        ),
                      ),
                    );
                  },
                );
              },
            ),
    );
  }
}

class CadastroCameraPage extends StatefulWidget {
  final List<CameraDescription> cameras;
  final int usuarioId;
  final String nomeUsuario;

  const CadastroCameraPage({
    super.key,
    required this.cameras,
    required this.usuarioId,
    required this.nomeUsuario,
  });

  @override
  State<CadastroCameraPage> createState() => _CadastroCameraPageState();
}

class _CadastroCameraPageState extends State<CadastroCameraPage> {
  CameraController? controller;
  List<XFile> fotos = [];
  int quantidadeFotos = 0;

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
    if (controller == null ||
        !controller!.value.isInitialized ||
        quantidadeFotos >= 5) {
      return;
    }

    final imagem = await controller!.takePicture();

    if (!mounted) {
      return;
    }

    setState(() {
      fotos.add(imagem);
      quantidadeFotos++;
    });
  }

  Future<void> finalizarCadastro() async {
    try {
      // 1. Inicia o cadastro no backend
      final inicio = await http.post(
        Uri.parse('$apiUrl/iniciar_cadastro'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'nome': widget.nomeUsuario}),
      );

      if (inicio.statusCode != 200) {
        if (!mounted) {
          return;
        }

        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Não foi possível iniciar o cadastro.')),
        );

        return;
      }

      // 2. Envia as 5 fotos, uma por vez
      for (int i = 0; i < fotos.length; i++) {
        final bytes = await fotos[i].readAsBytes();
        final imagemBase64 = base64Encode(bytes);

        final resposta = await http.post(
          Uri.parse('$apiUrl/adicionar_foto'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'nome': widget.nomeUsuario,
            'imagem': imagemBase64,
          }),
        );

        if (resposta.statusCode != 200) {
          if (!mounted) {
            return;
          }

          final dados = jsonDecode(resposta.body);

          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(dados['erro'] ?? 'Erro ao enviar a foto ${i + 1}.'),
            ),
          );

          return;
        }
      }

      // 3. Finaliza o cadastro
      final finalizacao = await http.post(
        Uri.parse('$apiUrl/finalizar_cadastro'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'nome': widget.nomeUsuario}),
      );

      if (!mounted) {
        return;
      }

      if (finalizacao.statusCode == 200) {
        final dados = jsonDecode(finalizacao.body);

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              dados['mensagem'] ?? 'Cadastro realizado com sucesso!',
            ),
          ),
        );

        Navigator.pop(context);
      } else {
        final dados = jsonDecode(finalizacao.body);

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(dados['erro'] ?? 'Erro ao finalizar cadastro.'),
          ),
        );
      }
    } catch (e) {
  if (!mounted) {
    return;
  }

  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text('Erro: $e'),
      ));
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
        appBar: AppBar(title: const Text('Cadastro Facial')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Cadastro Facial'), centerTitle: true),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Text(
                  widget.nomeUsuario,
                  style: const TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                ),

                const SizedBox(height: 8),

                Text(
                  quantidadeFotos < 5
                      ? 'Foto ${quantidadeFotos + 1} de 5'
                      : '5 fotos capturadas',
                  style: const TextStyle(fontSize: 18),
                ),
              ],
            ),
          ),

          Expanded(child: CameraPreview(controller!)),

         Padding(
            padding: const EdgeInsets.all(20),
            child: quantidadeFotos < 5
                ? ElevatedButton(
                    onPressed: tirarFoto,
                    child: const Text('TIRAR FOTO'),
                  )
                : ElevatedButton(
                    onPressed: finalizarCadastro,
                    child: const Text('FINALIZAR CADASTRO'),
                  ),
          ),
        ],
      ),
    );
  }
}

class ReconhecimentoPage extends StatefulWidget {
  final List<CameraDescription> cameras;

  const ReconhecimentoPage({super.key, required this.cameras});

  @override
  State<ReconhecimentoPage> createState() => _ReconhecimentoPageState();
}

class _ReconhecimentoPageState extends State<ReconhecimentoPage> {
  CameraController? controller;
  bool reconhecendo = false;

  String? nomeReconhecido;
  String? mensagem;

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

  Future<void> reconhecerFace() async {
    if (controller == null ||
        !controller!.value.isInitialized ||
        reconhecendo) {
      return;
    }

    setState(() {
      reconhecendo = true;
      nomeReconhecido = null;
      mensagem = null;
    });

    try {
      final imagem = await controller!.takePicture();

      final bytes = await imagem.readAsBytes();
      final imagemBase64 = base64Encode(bytes);

      final resposta = await http.post(
        Uri.parse('$apiUrl/reconhecer'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'imagem': imagemBase64}),
      );

      if (!mounted) {
        return;
      }

      final dados = jsonDecode(resposta.body);

      if (resposta.statusCode == 200) {
        setState(() {
          nomeReconhecido = dados['nome'];
          mensagem = 'Rosto reconhecido com sucesso!';
          reconhecendo = false;
        });
      } else {
        setState(() {
          mensagem = dados['erro'] ?? 'Rosto não reconhecido.';
          reconhecendo = false;
        });
      }
    } catch (e) {
      if (!mounted) {
        return;
      }

      setState(() {
        mensagem = 'Não foi possível conectar à API.';
        reconhecendo = false;
      });
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
        appBar: AppBar(title: const Text('Reconhecimento Facial')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Reconhecimento Facial'),
        centerTitle: true,
      ),
      body: Column(
        children: [
          Expanded(child: CameraPreview(controller!)),

          if (nomeReconhecido != null)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                nomeReconhecido!,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),

          if (mensagem != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                mensagem!,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 16),
              ),
            ),

          Padding(
            padding: const EdgeInsets.all(20),
            child: ElevatedButton(
              onPressed: reconhecendo ? null : reconhecerFace,
              child: reconhecendo
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('RECONHECER'),
            ),
          ),
        ],
      ),
    );
  }
}
