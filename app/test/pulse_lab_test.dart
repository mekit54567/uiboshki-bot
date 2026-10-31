import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/screens/pulse_lab.dart';

void main() {
  test('Пульс: где мы и что обход не открывает', () {
    expect(onPulse('https://pulse.mirea.ru/lessons/visiting-logs'), isTrue);
    expect(onPulse('https://pulse.mirea.ru/login'), isFalse);
    expect(onPulse('https://sso.mirea.ru/realms/x/protocol/openid-connect/auth'), isFalse);
    expect(pulseSkip.hasMatch('/lessons/visiting-logs/selfapprove'), isTrue);
    expect(pulseSkip.hasMatch('/logout'), isTrue);
    expect(pulseSkip.hasMatch('/students-self-approve/abc'), isTrue);
    expect(pulseSkip.hasMatch('/services/maps'), isFalse);
    expect(pulseAgo(45 * 60000), '45 мин');
    expect(pulseAgo((3 * 60 + 20) * 60000), '3 ч 20 мин');
    expect(pulseAgo((50 * 60) * 60000), '2 дн 2 ч');
    expect(jsString('"{\\"a\\":1}"'), '{"a":1}');
    expect(jsString('12'), '12');
    expect(pulseGoJs('/x"y'), contains('"/x\\"y"'));
  });
}
