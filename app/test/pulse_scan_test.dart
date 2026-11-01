import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/screens/pulse_scan.dart';

void main() {
  const t = '01a04906-839e-7381-bb78-2a9f41f05f37';

  test('только QR отметки Пульса', () {
    expect(pulseSelfApprove('https://pulse.mirea.ru/lessons/visiting-logs/selfapprove?token=$t'), isNotNull);
    expect(pulseSelfApprove('http://pulse.mirea.ru/lessons/visiting-logs/selfapprove?token=$t'), isNull);
    expect(pulseSelfApprove('https://evil.ru/lessons/visiting-logs/selfapprove?token=$t'), isNull);
    expect(pulseSelfApprove('https://pulse.mirea.ru/logout?token=$t'), isNull);
    expect(pulseSelfApprove('https://pulse.mirea.ru/lessons/visiting-logs/selfapprove?token=<script>'), isNull);
    expect(pulseSelfApprove(null), isNull);
  });

  test('итог отметки', () {
    const page = 'https://pulse.mirea.ru/lessons/visiting-logs/selfapprove?token=x';
    expect(pulseMarkOf('', page, [
      {'url': 'https://pulse.mirea.ru/x.AttendanceService/SelfApproveAttendance', 'status': 200, 'grpc': '0'},
    ]), PulseMark.ok);
    expect(pulseMarkOf('', page, [
      {'url': 'https://pulse.mirea.ru/x.AttendanceService/SelfApproveAttendance', 'status': 200, 'grpc': '9'},
    ]), PulseMark.failed);
    expect(pulseMarkOf('Вы отмечены на занятии', page, []), PulseMark.ok);
    expect(pulseMarkOf('Срок действия QR-кода истёк', page, []), PulseMark.failed);
    expect(pulseMarkOf('', 'https://sso.mirea.ru/realms/x/login', []), PulseMark.login);
    expect(pulseMarkOf('Загрузка', page, []), PulseMark.unknown);
  });
}
