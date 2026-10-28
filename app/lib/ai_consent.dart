// Согласие перед первым вопросом к ИИ (правило App Store 5.1.2(i)): до того
// как текст, фото или файл уйдут сторонним сервисам ИИ, человек видит, что и
// кому уходит, и сам соглашается. Только в приложении на iPhone: на Android и
// в вебе это уже сказано в согласии на обработку данных (legal_texts.py).
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'widgets/common.dart';

const aiConsentKey = 'ai_consent';

const aiConsentText =
    'Чтобы ответить, Kapi ИИ отправляет текст вопроса, приложенное фото или файл и подходящие куски '
    'лекций группы сторонним сервисам ИИ: OpenRouter, Inc. и Google LLC (США). Твоё имя, почта и вход '
    'в СДО туда не уходят. Не присылай лишнего о себе и о других — например, фото документов. '
    'Подробнее — в Политике конфиденциальности (Ещё → Безопасность).';

bool get aiConsentNeeded => !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;

/// true — можно отправлять: согласие уже есть или человек только что дал его.
Future<bool> ensureAiConsent(BuildContext context) async {
  if (!aiConsentNeeded) return true;
  final prefs = await SharedPreferences.getInstance();
  if (prefs.getBool(aiConsentKey) ?? false) return true;
  if (!context.mounted) return false;
  final ok = await confirmSheet(
    context,
    title: 'Вопрос уйдёт сервису ИИ',
    text: aiConsentText,
    action: 'Согласен',
    cancel: 'Не сейчас',
  );
  if (ok) await prefs.setBool(aiConsentKey, true);
  return ok;
}
