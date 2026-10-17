import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/api_config.dart';

void main() {
  test('development aceita o endereço especial do emulador Android', () {
    final uri = ApiConfig.validate(
      appEnvironment: 'development',
      apiBaseUrl: 'http://10.0.2.2:5013',
    );

    expect(uri.host, '10.0.2.2');
    expect(uri.port, 5013);
  });

  test('production exige HTTPS', () {
    expect(
      () => ApiConfig.validate(
        appEnvironment: 'production',
        apiBaseUrl: 'http://api.example.com',
      ),
      throwsArgumentError,
    );
  });

  test('production rejeita endereços locais', () {
    for (final host in ['localhost', '127.0.0.1', '10.0.2.2']) {
      expect(
        () => ApiConfig.validate(
          appEnvironment: 'production',
          apiBaseUrl: 'https://$host:5013',
        ),
        throwsArgumentError,
      );
    }
  });

  test('production aceita a URL HTTPS do piloto AWS', () {
    final uri = ApiConfig.validate(
      appEnvironment: 'production',
      apiBaseUrl: 'https://frequenia-piloto.duckdns.org',
    );

    expect(uri.scheme, 'https');
  });

  test('rejeita ambiente e URL inválidos', () {
    expect(
      () => ApiConfig.validate(
        appEnvironment: 'staging',
        apiBaseUrl: 'https://api.example.com',
      ),
      throwsArgumentError,
    );
    expect(
      () => ApiConfig.validate(
        appEnvironment: 'development',
        apiBaseUrl: 'api.example.com',
      ),
      throwsArgumentError,
    );
  });
}
