import 'package:flutter/material.dart';

import '../auth/auth_controller.dart';
import '../core/api_client.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key, required this.controller});

  final AuthController controller;

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  String? failure;
  bool loading = false;

  Future<void> reload() async {
    if (loading) return;
    setState(() {
      loading = true;
      failure = null;
    });
    try {
      await widget.controller.reloadMe();
    } on ApiException catch (error) {
      if (mounted) setState(() => failure = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => failure = 'Não foi possível atualizar o perfil.');
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final profile = widget.controller.user ?? const <String, dynamic>{};
    return RefreshIndicator(
      onRefresh: reload,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            'Perfil',
            style: Theme.of(context).textTheme.headlineSmall
                ?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          const Text('Contexto confirmado pelo backend em /auth/me.'),
          if (failure != null) ...[
            const SizedBox(height: 16),
            Text(
              failure!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          const SizedBox(height: 20),
          Card(
            child: Column(
              children: [
                _ProfileItem(
                  label: 'Usuário',
                  value: profile['user_id']?.toString(),
                ),
                const Divider(height: 1),
                _ProfileItem(
                  label: 'Funcionário',
                  value: profile['funcionario_id']?.toString(),
                ),
                const Divider(height: 1),
                _ProfileItem(
                  label: 'Empresa',
                  value: profile['empresa_id']?.toString(),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'Nome, matrícula e dados organizacionais completos dependem de um endpoint JSON de perfil em uma fase futura.',
          ),
          const SizedBox(height: 20),
          FilledButton.tonalIcon(
            onPressed: loading ? null : reload,
            icon: loading
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
            label: const Text('Atualizar'),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: widget.controller.busy ? null : widget.controller.logout,
            icon: const Icon(Icons.logout),
            label: const Text('Sair da conta'),
          ),
        ],
      ),
    );
  }
}

class _ProfileItem extends StatelessWidget {
  const _ProfileItem({required this.label, required this.value});

  final String label;
  final String? value;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      title: Text(label),
      subtitle: Text(value?.isNotEmpty == true ? value! : 'Não informado'),
    );
  }
}
