import 'package:flutter/foundation.dart';

import '../core/api_client.dart';

enum AuthStatus { initializing, unauthenticated, authenticated }

class AuthController extends ChangeNotifier {
  AuthController(this.api) {
    api.onSessionExpired = _handleExpiredSession;
  }

  final ApiClient api;

  AuthStatus status = AuthStatus.initializing;
  bool busy = false;
  String? sessionMessage;
  Map<String, dynamic>? user;

  bool get isAuthenticated => status == AuthStatus.authenticated;

  Future<void> restoreSession() async {
    status = AuthStatus.initializing;
    sessionMessage = null;
    notifyListeners();
    try {
      user = await api.restoreSession();
      status = user == null
          ? AuthStatus.unauthenticated
          : AuthStatus.authenticated;
    } on ApiException catch (error) {
      user = null;
      status = AuthStatus.unauthenticated;
      sessionMessage = error.message;
    } catch (_) {
      user = null;
      status = AuthStatus.unauthenticated;
      sessionMessage = 'Não foi possível restaurar a sessão.';
    }
    notifyListeners();
  }

  Future<void> login(String cpf, String password) async {
    if (busy) return;
    busy = true;
    sessionMessage = null;
    notifyListeners();
    try {
      user = await api.login(cpf, password);
      status = AuthStatus.authenticated;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> reloadMe() async {
    user = await api.getMe();
    notifyListeners();
  }

  Future<void> logout() async {
    if (busy) return;
    busy = true;
    notifyListeners();
    try {
      await api.logout();
    } finally {
      user = null;
      status = AuthStatus.unauthenticated;
      busy = false;
      notifyListeners();
    }
  }

  void _handleExpiredSession() {
    user = null;
    status = AuthStatus.unauthenticated;
    sessionMessage = 'Sua sessão expirou. Entre novamente.';
    notifyListeners();
  }

  @override
  void dispose() {
    api.onSessionExpired = null;
    super.dispose();
  }
}
