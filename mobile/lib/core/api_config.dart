class ApiConfig {
  const ApiConfig._();

  static const Set<String> _validEnvironments = {
    'development',
    'homologation',
    'production',
  };

  static const String environment = String.fromEnvironment(
    'APP_ENV',
    defaultValue: 'development',
  );

  static const String baseUrl = String.fromEnvironment(
    'BASE_URL',
    defaultValue: 'http://10.0.2.2:5013',
  );

  static Uri validate({
    String appEnvironment = environment,
    String apiBaseUrl = baseUrl,
  }) {
    final normalizedEnvironment = appEnvironment.trim().toLowerCase();
    if (!_validEnvironments.contains(normalizedEnvironment)) {
      throw ArgumentError(
        'APP_ENV deve ser development, homologation ou production.',
      );
    }

    final uri = Uri.tryParse(apiBaseUrl.trim());
    if (uri == null ||
        !uri.hasScheme ||
        !uri.hasAuthority ||
        (uri.scheme != 'http' && uri.scheme != 'https')) {
      throw ArgumentError('BASE_URL deve ser uma URL HTTP(S) absoluta.');
    }

    if (normalizedEnvironment == 'production') {
      if (uri.scheme != 'https') {
        throw ArgumentError('BASE_URL deve usar HTTPS em production.');
      }
      if (_isLocalHost(uri.host)) {
        throw ArgumentError(
          'BASE_URL de production não pode apontar para um endereço local.',
        );
      }
    }

    return uri;
  }

  static bool _isLocalHost(String host) {
    final normalized = host.toLowerCase();
    return normalized == 'localhost' ||
        normalized == '127.0.0.1' ||
        normalized == '::1' ||
        normalized == '10.0.2.2';
  }
}
