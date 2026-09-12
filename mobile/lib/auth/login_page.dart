import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/api_client.dart';
import '../core/theme.dart';
import 'auth_controller.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key, required this.controller});
  final AuthController controller;
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final cpf = TextEditingController();
  final password = TextEditingController();
  final formKey = GlobalKey<FormState>();
  bool obscure = true;
  String? errorMessage;

  @override
  void dispose() {
    cpf.dispose();
    password.dispose();
    super.dispose();
  }

  Future<void> submit() async {
    if (!formKey.currentState!.validate()) return;
    setState(() => errorMessage = null);
    try {
      await widget.controller.login(cpf.text.trim(), password.text);
    } on ApiException catch (error) {
      if (mounted) setState(() => errorMessage = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => errorMessage = 'Não foi possível acessar o servidor.');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Form(
                key: formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Container(
                      width: 68,
                      height: 68,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          colors: [FrequenIAColors.navy, FrequenIAColors.cyan],
                        ),
                        borderRadius: BorderRadius.circular(22),
                      ),
                      child: const Icon(
                        Icons.face_retouching_natural_rounded,
                        color: Colors.white,
                        size: 34,
                      ),
                    ),
                    const SizedBox(height: 28),
                    Text(
                      'Bem-vindo ao\nFrequenIA',
                      style: Theme.of(context).textTheme.displaySmall?.copyWith(
                        fontWeight: FontWeight.w800,
                        color: Theme.of(context).colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Sua jornada, marcações e solicitações em um só lugar.',
                      style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 34),
                    TextFormField(
                      controller: cpf,
                      keyboardType: TextInputType.number,
                      autofillHints: const [AutofillHints.username],
                      inputFormatters: [
                        FilteringTextInputFormatter.digitsOnly,
                        LengthLimitingTextInputFormatter(11),
                      ],
                      decoration: const InputDecoration(
                        labelText: 'CPF',
                        prefixIcon: Icon(Icons.badge_outlined),
                      ),
                      validator: (value) =>
                          (value ?? '').replaceAll(RegExp(r'\D'), '').length ==
                              11
                          ? null
                          : 'Informe os 11 números do CPF',
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: password,
                      obscureText: obscure,
                      autofillHints: const [AutofillHints.password],
                      onFieldSubmitted: (_) => submit(),
                      decoration: InputDecoration(
                        labelText: 'Senha',
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          onPressed: () => setState(() => obscure = !obscure),
                          icon: Icon(
                            obscure
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                      ),
                      validator: (value) =>
                          (value ?? '').isEmpty ? 'Informe sua senha' : null,
                    ),
                    if (errorMessage != null ||
                        widget.controller.sessionMessage != null) ...[
                      const SizedBox(height: 14),
                      Semantics(
                        liveRegion: true,
                        child: Text(
                          errorMessage ?? widget.controller.sessionMessage!,
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 22),
                    FilledButton(
                      onPressed: widget.controller.busy ? null : submit,
                      child: widget.controller.busy
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : const Text('Entrar'),
                    ),
                    const SizedBox(height: 18),
                    const Text(
                      'Ambiente de homologação · Não substitui o ponto oficial',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
