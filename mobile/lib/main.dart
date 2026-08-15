import 'package:flutter/material.dart';

void main() {
  runApp(const FrequenciaApp());
}

class FrequenciaApp extends StatelessWidget {
  const FrequenciaApp({super.key});

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

// TELA INICIAL
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
            const Text(
              'Registro de Ponto',
              style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
            ),

            const SizedBox(height: 40),

            ElevatedButton(
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (context) => const CameraPage()),
                );
              },
              child: const Text('IR PARA CÂMERA'),
            ),
          ],
        ),
      ),
    );
  }
}

// TELA DA CÂMERA
class CameraPage extends StatelessWidget {
  const CameraPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Câmera'), centerTitle: true),

      body: Center(
        child: ElevatedButton(
          onPressed: () {
            // Futuramente vamos abrir a câmera aqui.
          },
          child: const Text('ABRIR CÂMERA'),
        ),
      ),
    );
  }
}
