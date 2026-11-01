import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:uiboshki/screens/pulse_scan.dart';
import 'package:uiboshki/theme/app_theme.dart';

import 'util.dart';

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

  testWidgets('подсказка и рамка — на весь экран, а не в полоске сверху', (t) async {
    // 01.11: Stack сжимался до высоты ряда кнопок — ниже был чёрный экран
    phone(t);
    await t.pumpWidget(AppStyle(
      p: Palette.notebook,
      font: FontChoice.book,
      child: MaterialApp(
        home: Scaffold(
          backgroundColor: Colors.black,
          body: Stack(
            fit: StackFit.expand,
            children: [
              Positioned.fill(child: PulseScanOverlay(hint: 'Наведи на QR', busy: false, onClose: () {}, onTorch: () {})),
            ],
          ),
        ),
      ),
    ));
    await t.pump();
    final hint = t.getRect(find.text('Наведи на QR'));
    expect(hint.top, greaterThan(844 * 0.5));
    expect(t.getRect(find.byKey(const Key('scan:close'))).top, lessThan(120));
  });
}
