// Один раз после входа, тура и группы — своё окно «Присылать расписание и
// сроки?» (Никита 02.11, вариант А). Системное окно iOS показывается только
// раз, поэтому зовём его лишь после «Включить»: отказ в нём включить потом
// можно только в Настройках телефона. Тумблер — в «Ещё → Уведомления».
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api.dart';
import '../app_push.dart';
import '../widgets/capy.dart';
import '../widgets/common.dart';

const pushAskedKey = 'uib_push_asked';

/// Спросить, если ещё не спрашивали и пуши на телефоне есть, но выключены.
Future<void> maybeAskPush(BuildContext context, Api api) async {
  if (AppPush.device == null) return;
  final prefs = await SharedPreferences.getInstance();
  if (prefs.getBool(pushAskedKey) == true) return;
  if (await AppPush.state(api) != 'off' || !context.mounted) return; // включены, запрещены или канала нет
  await prefs.setBool(pushAskedKey, true);
  final yes = await confirmSheet(
    context,
    title: 'Присылать расписание и сроки?',
    text: 'Утром — пары на день, перед парой — куда идти, а ещё напомню '
        'о сроке сдачи, пока не поздно. Текст уведомлений зашифрован. '
        'Выключить можно в «Ещё → Уведомления».',
    action: 'Включить',
    cancel: 'Не сейчас',
    child: const Center(child: _Capy()),
  );
  if (!yes || !context.mounted) return;
  try {
    final v = await AppPush.enable(api);
    if (!context.mounted) return;
    if (v == 'on') {
      showToast(context, 'Уведомления включены', kind: ToastKind.done);
    } else if (v == 'denied') {
      showToast(context, 'Запрещены в настройках телефона — разреши там, потом включи в «Ещё → Уведомления»');
    }
  } catch (e) {
    if (context.mounted) showToast(context, 'Не получилось: ${errorText(e)}', kind: ToastKind.error);
  }
}

class _Capy extends StatelessWidget {
  const _Capy();

  @override
  Widget build(BuildContext context) => const CapyImage(pose: CapyPose.morning, size: 120);
}
