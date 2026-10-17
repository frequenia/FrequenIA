import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/widgets.dart';

void main() {
  test('exibe todos os estados oficiais do workflow de correcoes', () {
    expect(statusLabel('pendente_gestor'), 'Pendente com gestor');
    expect(statusLabel('encaminhada_rh'), 'Encaminhada ao RH');
    expect(statusLabel('aprovada'), 'Aprovada');
    expect(statusLabel('rejeitada'), 'Rejeitada');
    expect(statusLabel('cancelada'), 'Cancelada');
  });
}
