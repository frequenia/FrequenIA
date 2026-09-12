# FrequenIA Mobile

Fundação Flutter do aplicativo FrequenIA. Nesta fase, o app oferece login,
restauração segura da sessão, refresh token rotativo, `/auth/me`, logout,
navegação autenticada e consulta da própria jornada em `/api/jornada`.

## Configuração da API

A URL do Flask é definida em compilação por `BASE_URL`; o ambiente pode ser
identificado por `APP_ENV`:

```powershell
flutter run --dart-define=APP_ENV=development --dart-define=BASE_URL=http://10.0.2.2:5007
```

- Emulador Android: `10.0.2.2` aponta para o computador host.
- Celular físico: informe o IP alcançável do computador na mesma rede, sem
  gravá-lo no código.
- Homologação/produção: informe a URL HTTPS correspondente no comando de build.

HTTP sem TLS é aceito apenas pelo manifesto Android de `debug`. Builds de
produção não recebem essa liberação.

## Verificação

```powershell
flutter pub get
flutter analyze
flutter test
```

O aplicativo não acessa o Supabase diretamente e não deve receber credenciais
do banco, `service_role`, chaves JWT ou segredos Flask.
