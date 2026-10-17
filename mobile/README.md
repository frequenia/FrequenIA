# FrequenIA Mobile

Fundação Flutter do aplicativo FrequenIA. Nesta fase, o app oferece login,
restauração segura da sessão, refresh token rotativo, `/auth/me`, logout,
navegação autenticada e consulta da própria jornada em `/api/jornada`.

O registro facial mobile exige localização precisa em primeiro plano. A unidade
deve estar explicitamente habilitada com coordenadas e raio no painel web. Se o
GPS ou o celular estiver indisponível, o funcionário deve usar o quiosque.

## Configuração da API

A URL do Flask é definida em compilação por `BASE_URL`; o ambiente pode ser
identificado por `APP_ENV`:

```powershell
flutter run --dart-define=APP_ENV=development --dart-define=BASE_URL=http://10.0.2.2:5013
```

- Emulador Android: `10.0.2.2` aponta para o computador host; com o Compose do
  projeto, use `http://10.0.2.2:5013`.
- Celular físico: informe o IP alcançável do computador na mesma rede, sem
  gravá-lo no código.
- Homologação/produção: informe a URL HTTPS correspondente no comando de build.

Em `production`, a inicialização recusa HTTP, localhost, `127.0.0.1` e
`10.0.2.2`. Exemplo:

```powershell
flutter build appbundle --dart-define=APP_ENV=production --dart-define=BASE_URL=https://URL_DO_CLOUD_RUN
```

HTTP sem TLS é aceito apenas pelo manifesto Android de `debug`. Builds de
produção não recebem essa liberação.

## Verificação

```powershell
flutter pub get
flutter analyze
flutter test
```

No Android, habilite o Developer Mode do Windows antes de resolver plugins
Flutter, pois o toolchain cria links simbólicos durante o build.

O aplicativo não acessa o Supabase diretamente e não deve receber credenciais
do banco, `service_role`, chaves JWT ou segredos Flask.
