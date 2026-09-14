import 'package:flutter/material.dart';

import '../auth/auth_controller.dart';
import '../core/api_client.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key, required this.controller, this.active = true});

  final AuthController controller;
  final bool active;

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  String? failure;
  bool loading = false;
  Map<String, dynamic>? profile;

  @override
  void initState() {
    super.initState();
    if (widget.active) reload();
  }

  @override
  void didUpdateWidget(covariant ProfilePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.active && !oldWidget.active && profile == null && !loading) {
      reload();
    }
  }

  Future<void> reload() async {
    if (loading) return;
    setState(() {
      loading = true;
      failure = null;
    });
    try {
      final result = await widget.controller.api.get('/api/perfil');
      if (mounted) setState(() => profile = result);
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
          const Text('Dados do seu vínculo confirmados pelo servidor.'),
          if (failure != null) ...[
            const SizedBox(height: 16),
            Text(
              failure!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          if (loading && profile == null) ...[
            const SizedBox(height: 28),
            const Center(child: CircularProgressIndicator()),
          ] else if (profile != null) ...[
            const SizedBox(height: 20),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Text(
                  _display(profile!['nome']),
                  style: Theme.of(context).textTheme.headlineSmall
                      ?.copyWith(fontWeight: FontWeight.w800),
                ),
              ),
            ),
            const SizedBox(height: 16),
            _ProfileSection(
              title: 'Dados pessoais',
              items: [
                _ProfileItem(
                  label: 'CPF',
                  value: _display(profile!['cpf_mascarado']),
                ),
                _ProfileItem(
                  label: 'Telefone',
                  value: _display(profile!['telefone']),
                ),
                _ProfileItem(
                  label: 'E-mail',
                  value: _display(profile!['email']),
                ),
              ],
            ),
            const SizedBox(height: 16),
            _ProfileSection(
              title: 'Vínculo funcional',
              items: [
                _ProfileItem(
                  label: 'Matrícula',
                  value: _display(profile!['matricula']),
                ),
                _ProfileItem(
                  label: 'Perfil',
                  value: _profileLabel(profile!['perfil']),
                ),
                _ProfileItem(
                  label: 'Empresa',
                  value: _display(profile!['empresa']),
                ),
                _ProfileItem(
                  label: 'Unidade',
                  value: _display(profile!['unidade']),
                ),
                _ProfileItem(
                  label: 'Equipe',
                  value: _display(profile!['equipe']),
                ),
                _ProfileItem(
                  label: 'Cargo',
                  value: _display(profile!['cargo']),
                ),
              ],
            ),
          ],
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
  final String value;

  @override
  Widget build(BuildContext context) {
    return ListTile(title: Text(label), subtitle: Text(value));
  }
}

String _display(dynamic value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? 'Não informado' : text;
}

String _profileLabel(dynamic value) => switch (value?.toString()) {
  'administrador' => 'Administrador',
  'funcionario' => 'Funcionário',
  'gestor' => 'Gestor',
  'rh' => 'RH',
  _ => _display(value),
};

class _ProfileSection extends StatelessWidget {
  const _ProfileSection({required this.title, required this.items});

  final String title;
  final List<_ProfileItem> items;

  @override
  Widget build(BuildContext context) => Card(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text(
            title,
            style: Theme.of(context).textTheme.titleMedium
                ?.copyWith(fontWeight: FontWeight.w800),
          ),
        ),
        for (var index = 0; index < items.length; index++) ...[
          if (index > 0) const Divider(height: 1),
          items[index],
        ],
      ],
    ),
  );
}
