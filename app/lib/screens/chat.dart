// Помощник: вопросы ИИ, который опирается на лекции группы. Можно выбрать
// предмет; под ответом — откуда взято («Лекция 4 · стр. 3»), нажал — страница.
// Вложение (фото или PDF/DOCX/PPTX/TXT до 10 МБ) уходит ИИ один раз, а текст
// документа (file_text с сервера) помнится в вопросе — следующие вопросы знают
// файл. Чаты — на телефоне (до 20, в каждом последние 40 сообщений), «Прошлые
// чаты» — листом, «Новый чат» — с нуля, старый остаётся в списке.
// Клавиатура — как в приложении Claude: переписка листается с открытой
// клавиатурой, убирает её палец, доведённый до поля ввода, смахивание поля
// вниз или нажатие на переписку; низ переписки при этом не уезжает.
import 'dart:async';
import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api.dart';
import '../api/models.dart' show monthsShort, plural;
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';
import '../widgets/tg_html.dart';
import 'files.dart';

class ChatMsg {
  final String role, content, html;
  final List<Map<String, dynamic>> sources, files;
  final List<String> choose;
  final bool error;

  /// Вложение вопроса: имя и фото ли (сами байты не храним).
  final ({String name, bool image})? att;

  /// Текст вложенного документа — уходит в историю следующих вопросов.
  String fileText;

  /// Вопрос без ответа (ошибка) — в историю не идёт, иначе ИИ отвечал на него позже.
  bool failed;

  /// Кнопка «Подумать ещё» под ответом (подписка): {label, left, daily}.
  final Map<String, dynamic>? think;

  ChatMsg(
    this.role,
    this.content, {
    this.html = '',
    this.sources = const [],
    this.files = const [],
    this.choose = const [],
    this.error = false,
    this.att,
    this.fileText = '',
    this.failed = false,
    this.think,
  });

  Map<String, dynamic> toJson() => {
    'role': role,
    'content': content,
    if (html.isNotEmpty) 'html': html,
    if (sources.isNotEmpty) 'sources': sources,
    if (files.isNotEmpty) 'files': files,
    if (att != null) 'att': {'name': att!.name, 'image': att!.image},
    if (fileText.isNotEmpty) 'file_text': fileText,
    if (failed) 'failed': true,
    if (think != null) 'think': think,
  };

  factory ChatMsg.fromJson(Map<String, dynamic> j) {
    final a = j['att'];
    return ChatMsg(
      j['role'] ?? 'user',
      j['content'] ?? '',
      html: j['html'] ?? '',
      sources: [for (final s in (j['sources'] as List? ?? [])) Map<String, dynamic>.from(s)],
      files: [for (final f in (j['files'] as List? ?? [])) Map<String, dynamic>.from(f)],
      att: a is Map ? (name: '${a['name'] ?? 'файл'}', image: a['image'] == true) : null,
      fileText: j['file_text'] ?? '',
      failed: j['failed'] == true,
      think: j['think'] is Map ? Map<String, dynamic>.from(j['think']) : null,
    );
  }
}

/// Вложение, которое ещё не ушло.
class ChatAttachment {
  final String name, mime;
  final Uint8List bytes;
  const ChatAttachment(this.name, this.mime, this.bytes);
  bool get image => mime.startsWith('image/');
}

/// Выбор вложения — системным окном; в тестах подменяется.
typedef PickAttachment = Future<ChatAttachment?> Function();

const maxAttachmentBytes = 10 * 1024 * 1024;

const _mimes = {
  'jpg': 'image/jpeg',
  'jpeg': 'image/jpeg',
  'png': 'image/png',
  'webp': 'image/webp',
  'heic': 'image/heic',
  'pdf': 'application/pdf',
  'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'txt': 'text/plain',
};

String mimeOf(String name) => _mimes[name.split('.').last.toLowerCase()] ?? '';

Future<ChatAttachment?> systemPickAttachment() async {
  final files = await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: _mimes.keys.toList());
  if (files.isEmpty) return null;
  final f = files.first;
  return ChatAttachment(f.name, mimeOf(f.name), await f.xFile.readAsBytes());
}

/// Чаты на телефоне — как в WebApp: до 20 последних разговоров, только текст
/// (без вложений). Ключ — с приставкой кэша API: «выйти» стирает и их.
/// `current` — открытый чат; '' — нажали «Новый чат» и ещё ничего не написали
/// (тогда при следующем заходе открывается пустой, а не старый).
const chatsStoreKey = 'uib_cache:chats';

/// Прежняя одна история ({log, subject}) — переезжает первым чатом.
const chatLegacyKey = 'uib_cache:chat';
const chatKeep = 40;
const chatsMax = 20;

/// Прошлый разговор: заголовок — начало первого вопроса.
class ChatThread {
  final String id;
  String title, subject;
  DateTime updated;
  List<Map<String, dynamic>> log;

  ChatThread({required this.id, required this.title, required this.updated, required this.log, this.subject = ''});

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'updated': updated.millisecondsSinceEpoch,
    'log': log,
    'subject': subject,
  };

  factory ChatThread.fromJson(Map<String, dynamic> j) => ChatThread(
    id: '${j['id']}',
    title: '${j['title'] ?? 'Новый чат'}',
    updated: DateTime.fromMillisecondsSinceEpoch((j['updated'] as num?)?.toInt() ?? 0),
    log: [for (final m in (j['log'] as List? ?? [])) Map<String, dynamic>.from(m)],
    subject: '${j['subject'] ?? ''}',
  );
}

/// Заголовок чата — начало первого вопроса (как в WebApp, до 60 знаков).
String chatTitle(List<Map<String, dynamic>> log) {
  for (final m in log) {
    final c = '${m['content'] ?? ''}'.trim();
    if (m['role'] == 'user' && c.isNotEmpty) return c.length > 60 ? c.substring(0, 60) : c;
  }
  return 'Новый чат';
}

/// «сегодня, 14:05» / «вчера» / «12 окт» — когда писали в чат.
String chatWhen(DateTime d, DateTime today) {
  final diff = DateTime(today.year, today.month, today.day).difference(DateTime(d.year, d.month, d.day)).inDays;
  if (diff == 0) return 'сегодня, ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
  if (diff == 1) return 'вчера';
  return '${d.day} ${monthsShort[d.month - 1]}${d.year != today.year ? ' ${d.year}' : ''}';
}

class ChatScreen extends StatefulWidget {
  final Api api;
  final PickAttachment pick;
  const ChatScreen({super.key, required this.api, this.pick = systemPickAttachment});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with WidgetsBindingObserver {
  /// Открытый разговор. Новый список при каждой смене чата: ответ на вопрос из
  /// прошлого чата сверяется с ним и уходит в свой чат, а не в открытый.
  var _log = <ChatMsg>[];
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final _bar = GlobalKey();
  String _subject = '';
  List<String> _subjects = [];
  bool _waiting = false;
  ChatAttachment? _att;
  String? _attNote; // «больше 10 МБ» и т. п.

  /// Прошлые чаты, свежие сверху; [_id] — открытый (null — новый, ещё без вопросов).
  List<ChatThread> _chats = [];
  String? _id;

  /// Есть несохранённое (вопрос ждёт ответа, сменили предмет) — сохранить, уходя из чата.
  bool _dirty = false;

  /// Пока чаты не прочитаны с телефона, не пишем — иначе затрём их.
  late final Future<void> _ready = _restore();

  /// Сколько вопросов осталось сегодня (сервер, ai_quota.left); null — без
  /// лимита (староста) или сервер не сказал — число не показываем.
  int? _left;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _ready;
    widget.api
        .get('/subjects')
        .then((j) {
          if (!mounted) return;
          setState(() {
            _subjects = [
              for (final s in j['subjects'] as List)
                if (s['lectures'] == true) s['name'] as String,
            ];
            final q = j['quota'];
            _left = q is Map && q['left'] is num ? (q['left'] as num).toInt() : null;
          });
        })
        .catchError((_) {});
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  /// Клавиатура выезжает или уходит — окно меняет высоту. Были внизу
  /// переписки — остаёмся внизу, последний ответ не прячется за клавиатуру.
  @override
  void didChangeMetrics() {
    if (!_scroll.hasClients) return;
    final pos = _scroll.position;
    if (pos.pixels < pos.maxScrollExtent - 48) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  Future<void> _restore() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      var chats = <ChatThread>[];
      String? current;
      final raw = prefs.getString(chatsStoreKey);
      if (raw != null) {
        final j = jsonDecode(raw) as Map<String, dynamic>;
        chats = [for (final c in j['chats'] as List? ?? []) ChatThread.fromJson(Map<String, dynamic>.from(c))];
        current = j['current'] as String?;
      } else {
        final old = prefs.getString(chatLegacyKey);
        if (old != null) {
          // прежняя одна история — первым чатом, он и откроется
          final j = jsonDecode(old) as Map<String, dynamic>;
          final log = [for (final m in j['log'] as List? ?? []) Map<String, dynamic>.from(m)];
          if (log.isNotEmpty) {
            final c = ChatThread(
              id: 'c${now().microsecondsSinceEpoch}',
              title: chatTitle(log),
              updated: now(),
              log: log,
              subject: '${j['subject'] ?? ''}',
            );
            chats = [c];
            current = c.id;
          }
          await prefs.setString(chatsStoreKey, jsonEncode({'chats': chats, 'current': current ?? ''}));
          await prefs.remove(chatLegacyKey);
        }
      }
      if (!mounted) return;
      final open = current == null ? chats.firstOrNull : chats.where((c) => c.id == current).firstOrNull;
      setState(() {
        _chats = chats;
        // пока читали, человек уже начал писать — его разговор не трогаем
        if (open != null && _log.isEmpty && _id == null) _open(open);
      });
      _toEnd();
    } catch (_) {}
  }

  /// Открыть сохранённый чат (без setState — его зовут внутри).
  void _open(ChatThread c) {
    _id = c.id;
    _log = [for (final m in c.log) ChatMsg.fromJson(m)];
    _subject = c.subject;
    _dirty = false;
  }

  Future<void> _persist() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(chatsStoreKey, jsonEncode({'chats': _chats, 'current': _id ?? ''}));
    } catch (_) {}
  }

  /// Записать разговор [log] в чат [id] (null — новый) и поднять его наверх.
  /// Ошибки и «по какому предмету?» не храним — это не разговор. Возвращает
  /// id чата; null — нечего хранить в новом или чат уже удалили.
  String? _store(String? id, List<ChatMsg> log, String subject, {bool create = true}) {
    final keep = [
      for (final m in log)
        if (!m.error && m.choose.isEmpty) m.toJson(),
    ];
    var c = id == null ? null : _chats.where((x) => x.id == id).firstOrNull;
    if (keep.isEmpty) return c?.id;
    if (c == null) {
      if (!create) return null; // чат удалили, пока ждали ответ
      c = ChatThread(id: id ?? 'c${now().microsecondsSinceEpoch}', title: '', updated: now(), log: const []);
    }
    final t = c
      ..log = keep.length > chatKeep ? keep.sublist(keep.length - chatKeep) : keep
      ..title = chatTitle(keep)
      ..subject = subject
      ..updated = now();
    _chats = [t, ..._chats.where((x) => x.id != t.id)].take(chatsMax).toList();
    return t.id;
  }

  /// Сохранить открытый чат.
  Future<void> _save() async {
    await _ready;
    if (!mounted) return;
    _id = _store(_id, _log, _subject);
    _dirty = false;
    await _persist();
  }

  /// Уходя из чата (в новый, в другой): несохранённое — в свой чат.
  Future<void> _leave() async {
    if (_dirty) await _save();
  }

  Future<void> _newChat() async {
    tick();
    await _leave();
    if (!mounted) return;
    setState(() {
      _id = null;
      _log = [];
      _att = null;
      _attNote = null;
      _waiting = false;
      _input.clear();
    });
    await _persist();
  }

  Future<void> _switchTo(ChatThread c) async {
    if (c.id == _id) return;
    await _leave();
    if (!mounted) return;
    setState(() {
      _open(c);
      _att = null;
      _attNote = null;
      _waiting = false;
      _input.clear();
    });
    await _persist();
    _toEnd();
  }

  Future<void> _delete(ChatThread c) async {
    await _ready;
    if (!mounted) return;
    setState(() {
      _chats = [
        for (final x in _chats)
          if (x.id != c.id) x,
      ];
      if (c.id == _id) {
        _id = null;
        _log = [];
        _waiting = false;
        _dirty = false;
      }
    });
    await _persist();
  }

  /// «Прошлые чаты» — листом снизу: открыть, удалить (крестик или смахнуть), новый.
  Future<void> _openChats() async {
    tick();
    if (_dirty) await _save(); // открытый — в списке вместе со своим вопросом
    if (!mounted) return;
    final picked = await appSheet<Object>(
      context,
      (ctx) => _ChatsSheet(chats: _chats, current: _id, canNew: _log.isNotEmpty, onDelete: _delete),
    );
    if (!mounted) return;
    if (picked is ChatThread) {
      tick();
      await _switchTo(picked);
    } else if (picked == _ChatsSheet.newChat) {
      await _newChat();
    }
  }

  Future<void> _attach() async {
    tick();
    final ChatAttachment? a;
    try {
      a = await widget.pick();
    } catch (_) {
      return;
    }
    if (a == null || !mounted) return;
    setState(() {
      if (a!.bytes.length > maxAttachmentBytes) {
        _att = null;
        _attNote = 'Файл больше 10 МБ — не пролезет.';
      } else if (a.mime.isEmpty) {
        _att = null;
        _attNote = 'Умею читать PDF, DOCX, PPTX и TXT, а ещё фото.';
      } else {
        _att = a;
        _attNote = null;
      }
    });
  }

  Future<void> _send({String? again, ChatAttachment? againAtt}) async {
    final text = again ?? _input.text.trim();
    final att = again != null ? againAtt : _att;
    if ((text.isEmpty && att == null) || _waiting) return;
    tick();
    final log = _log; // ответ — в этот разговор, даже если открыли другой
    _id ??= 'c${now().microsecondsSinceEpoch}';
    final id = _id;
    ChatMsg entry;
    if (again == null) {
      // В истории — только текст; само вложение уходит отдельным полем.
      entry = ChatMsg(
        'user',
        text.isNotEmpty ? text : (att!.image ? 'Реши задание на фото.' : 'Разбери этот файл.'),
        att: att == null ? null : (name: att.name, image: att.image),
      );
      _log.add(entry);
      _dirty = true;
    } else {
      entry = _log.lastWhere((m) => m.role == 'user');
    }
    setState(() {
      entry.failed = false;
      _input.clear();
      _att = null;
      _attNote = null;
      _waiting = true;
    });
    _toEnd();
    final body = <String, dynamic>{'history': _history(_log), 'subject': _subject};
    if (att != null) body['attachment'] = {'name': att.name, 'mime': att.mime, 'data': base64Encode(att.bytes)};
    ChatMsg answer;
    try {
      final r = await widget.api.post('/chat', body);
      if (r['file_text'] is String) entry.fileText = r['file_text'];
      final choose = [for (final c in (r['choose'] as List? ?? [])) '$c'];
      answer = ChatMsg(
        'assistant',
        r['content'] ?? '',
        html: r['html'] ?? '',
        sources: [for (final s in (r['sources'] as List? ?? [])) Map<String, dynamic>.from(s)],
        files: [for (final f in (r['files'] as List? ?? [])) Map<String, dynamic>.from(f)],
        choose: choose,
        think: r['think'] is Map ? Map<String, dynamic>.from(r['think']) : null,
      );
      if (choose.isNotEmpty) _chooseAtt = att; // выберет предмет — вложение уйдёт ещё раз
      if (_left != null && _left! > 0 && choose.isEmpty && answer.files.isEmpty) _left = _left! - 1;
    } on ApiError catch (e) {
      entry.failed = true;
      answer = ChatMsg('assistant', e.message, error: true);
    } catch (e) {
      entry.failed = true;
      answer = ChatMsg('assistant', errorText(e), error: true);
    }
    await _deliver(log, id, answer);
  }

  /// История для сервера: без ошибок и вопросов без ответа; два ответа
  /// подряд («Подумать ещё») — только последний, роли чередуются.
  List<Map<String, String>> _history(List<ChatMsg> log) {
    final ok = [
      for (final m in log)
        if (!m.error && !m.failed && m.content.isNotEmpty && m.choose.isEmpty) m,
    ];
    return [
      for (var i = 0; i < ok.length; i++)
        if (!(ok[i].role == 'assistant' && i + 1 < ok.length && ok[i + 1].role == 'assistant'))
          {
            'role': ok[i].role,
            'content': ok[i].fileText.isEmpty ? ok[i].content : '${ok[i].content}\n\n${ok[i].fileText}',
          },
    ];
  }

  /// «Подумать ещё»: тот же вопрос заново решает модель второго уровня
  /// (подписка, свой дневной лимит); новый ответ — под прежним.
  Future<void> _think() async {
    if (_waiting || _log.length < 2 || _log.last.role != 'assistant') return;
    tick();
    final log = _log;
    final id = _id;
    setState(() => _waiting = true);
    _toEnd();
    final body = {'history': _history(_log.sublist(0, _log.length - 1)), 'subject': _subject, 'think': true};
    ChatMsg answer;
    try {
      final r = await widget.api.post('/chat', body);
      answer = ChatMsg(
        'assistant',
        r['content'] ?? '',
        html: r['html'] ?? '',
        sources: [for (final s in (r['sources'] as List? ?? [])) Map<String, dynamic>.from(s)],
        think: r['think'] is Map ? Map<String, dynamic>.from(r['think']) : null,
      );
    } on ApiError catch (e) {
      answer = ChatMsg('assistant', e.message, error: true);
    } catch (e) {
      answer = ChatMsg('assistant', errorText(e), error: true);
    }
    await _deliver(log, id, answer);
  }

  Future<void> _deliver(List<ChatMsg> log, String? id, ChatMsg answer) async {
    if (!mounted) return;
    if (!identical(log, _log)) {
      // пока ждали, ушли в другой чат — ответ в свой (если его не удалили)
      await _ready;
      final c = _chats.where((x) => x.id == id).firstOrNull;
      if (c == null || !mounted) return;
      log.add(answer);
      _store(id, log, c.subject, create: false);
      if (_id == id) setState(() => _open(c)); // уже вернулись в него
      await _persist();
      return;
    }
    setState(() {
      _log.add(answer);
      _waiting = false;
    });
    _save();
    _toEnd();
  }

  ChatAttachment? _chooseAtt;

  Widget _thinkChip(AppStyle s, Map<String, dynamic> t) {
    final p = s.p;
    final left = (t['left'] as num?)?.toInt() ?? 0;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.s),
      child: Align(
        alignment: Alignment.centerLeft,
        child: ActionChip(
          onPressed: left > 0 ? _think : null,
          backgroundColor: p.card,
          side: BorderSide(color: left > 0 ? p.accent : p.line),
          shape: const StadiumBorder(),
          avatar: Icon(Icons.psychology_outlined, size: 18, color: p.accent),
          label: Text('${t['label'] ?? 'Подумать ещё'} · $left', style: s.body(13, weight: FontWeight.w600)),
        ),
      ),
    );
  }

  void _toEnd() => WidgetsBinding.instance.addPostFrameCallback((_) {
    if (_scroll.hasClients) {
      _scroll.animateTo(
        _scroll.position.maxScrollExtent + 200,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOutCubic,
      );
    }
  });

  Future<void> _pickSubject() async {
    final s = AppStyle.of(context);
    final picked = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: s.p.cardSolid,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (ctx) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(ctx).height * 0.7),
          child: ListView(
            shrinkWrap: true,
            children: [
              for (final name in ['', ..._subjects])
                ListTile(
                  title: Text(name.isEmpty ? 'Все предметы' : name, style: s.body(15)),
                  trailing: name == _subject ? Icon(Icons.check_rounded, color: s.p.accent) : null,
                  onTap: () => Navigator.pop(ctx, name),
                ),
            ],
          ),
        ),
      ),
    );
    if (picked != null && picked != _subject) {
      setState(() {
        _subject = picked;
        _dirty = _log.isNotEmpty;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Scaffold(
      body: Backdrop(
        child: SafeArea(
          child: Column(
            children: [
              Row(
                children: [
                  const BackRow(),
                  // узкий экран и крупный шрифт — название предмета сжимается, кнопки не съезжают
                  Expanded(
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        if (_chats.isNotEmpty)
                          IconButton(
                            tooltip: 'Прошлые чаты',
                            onPressed: _openChats,
                            icon: Icon(Icons.history_rounded, color: p.text),
                          ),
                        if (_log.isNotEmpty)
                          IconButton(
                            tooltip: 'Новый чат',
                            onPressed: _newChat,
                            icon: Icon(Icons.add_comment_outlined, color: p.text),
                          ),
                        Flexible(
                          child: Padding(
                            padding: const EdgeInsets.only(right: Space.l),
                            child: ActionChip(
                              onPressed: _pickSubject,
                              backgroundColor: p.card,
                              side: BorderSide(color: p.line),
                              shape: const StadiumBorder(),
                              avatar: Icon(Icons.menu_book_outlined, size: 16, color: p.accent),
                              label: ConstrainedBox(
                                constraints: const BoxConstraints(maxWidth: 170),
                                child: Text(
                                  _subject.isEmpty ? 'Все предметы' : _subject,
                                  overflow: TextOverflow.ellipsis,
                                  style: s.body(13, weight: FontWeight.w600),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              Expanded(
                child: KeyboardDragDismiss(
                  barKey: _bar,
                  child: GestureDetector(
                    // нажатие на переписку (не на кнопку в ней) убирает клавиатуру
                    onTap: () => FocusManager.instance.primaryFocus?.unfocus(),
                    child: ListView(
                      controller: _scroll,
                      padding: const EdgeInsets.only(bottom: Space.l),
                      children: [
                        const ScreenTitle(title: 'Помощник'),
                        if (_log.isEmpty) _Intro(left: _left),
                        if (_log.isEmpty)
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: Space.xl),
                            child: Wrap(
                              spacing: Space.s,
                              runSpacing: Space.s,
                              children: [
                                for (final q in const [
                                  'Чем метрика отличается от KPI?',
                                  'Объясни 3 лекцию',
                                  'Что сдать на этой неделе?',
                                ])
                                  ActionChip(
                                    backgroundColor: p.card,
                                    side: BorderSide(color: p.line),
                                    shape: const StadiumBorder(),
                                    // у чипа текст в одну строку и обрезается молча — переносим
                                    label: Text(q, softWrap: true, maxLines: 3, style: s.body(13)),
                                    onPressed: () {
                                      _input.text = q;
                                      _send();
                                    },
                                  ),
                              ],
                            ),
                          ),
                        for (final m in _log)
                          _Bubble(
                            m: m,
                            api: widget.api,
                            onChoose: (subj) {
                              setState(() => _subject = subj);
                              final lastQ = _log.lastWhere((x) => x.role == 'user');
                              _send(again: lastQ.content, againAtt: _chooseAtt);
                            },
                          ),
                        if (!_waiting && _log.isNotEmpty && _log.last.think != null) _thinkChip(s, _log.last.think!),
                        if (_waiting)
                          Padding(
                            padding: const EdgeInsets.fromLTRB(Space.xl, Space.s, Space.xl, 0),
                            child: Text('Думаю…', style: s.eyebrow()),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
              if (_att != null || _attNote != null)
                _AttachPreview(
                  att: _att,
                  note: _attNote,
                  onClear: () => setState(() {
                    _att = null;
                    _attNote = null;
                  }),
                ),
              KeyboardDragDismiss(
                barKey: _bar,
                child: _InputBar(key: _bar, controller: _input, busy: _waiting, onSend: _send, onAttach: _attach),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Лист «Прошлые чаты»: свежие сверху, открытый — с рамкой цвета темы.
/// Нажал — открыть (лист отдаёт ChatThread), крестик или смахнуть влево —
/// удалить, «Новый чат» — отдаёт [newChat].
class _ChatsSheet extends StatefulWidget {
  static const newChat = 'new';
  final List<ChatThread> chats;
  final String? current;
  final bool canNew;
  final ValueChanged<ChatThread> onDelete;
  const _ChatsSheet({required this.chats, required this.current, required this.canNew, required this.onDelete});

  @override
  State<_ChatsSheet> createState() => _ChatsSheetState();
}

class _ChatsSheetState extends State<_ChatsSheet> {
  late final _list = [...widget.chats];

  void _delete(ChatThread c) {
    tick();
    setState(() => _list.remove(c));
    widget.onDelete(c);
    if (_list.isEmpty) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final today = now();
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.75),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.m),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Прошлые чаты', style: s.title(22)),
                  const SizedBox(height: 4),
                  Text('Хранятся на этом телефоне — до $chatsMax последних.', style: s.body(13, color: p.muted)),
                ],
              ),
            ),
            if (widget.canNew)
              Padding(
                padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
                child: Tile(
                  key: const Key('chats:new'),
                  onTap: () => Navigator.pop(context, _ChatsSheet.newChat),
                  padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
                  child: Row(
                    children: [
                      Icon(Icons.add_comment_outlined, color: p.accent, size: 20),
                      const SizedBox(width: Space.m),
                      Expanded(
                        child: Text('Новый чат', style: s.body(15, weight: FontWeight.w600)),
                      ),
                    ],
                  ),
                ),
              ),
            Flexible(
              child: ListView(
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.l),
                children: [
                  for (final c in _list)
                    Padding(
                      key: ValueKey('chat:${c.id}'),
                      padding: const EdgeInsets.only(bottom: Space.s),
                      child: Dismissible(
                        key: ValueKey('chat-swipe:${c.id}'),
                        direction: DismissDirection.endToStart,
                        onDismissed: (_) => _delete(c),
                        background: Container(
                          alignment: Alignment.centerRight,
                          padding: const EdgeInsets.only(right: Space.xl),
                          decoration: BoxDecoration(color: p.danger, borderRadius: BorderRadius.circular(Radii.tile)),
                          child: Text(
                            'Удалить',
                            style: s.body(15, weight: FontWeight.w700, color: Colors.white),
                          ),
                        ),
                        child: Tile(
                          onTap: () => Navigator.pop(context, c),
                          border: c.id == widget.current ? p.accent : null,
                          padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.xs, Space.m),
                          child: Row(
                            children: [
                              Icon(Icons.chat_bubble_outline_rounded, color: p.accent, size: 20),
                              const SizedBox(width: Space.m),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      c.title,
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: s.body(15, weight: FontWeight.w600),
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      [
                                        chatWhen(c.updated, today),
                                        '${c.log.length} ${plural(c.log.length, 'сообщение', 'сообщения', 'сообщений')}',
                                        if (c.subject.isNotEmpty) c.subject,
                                      ].join(' · '),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: s.body(13, color: p.muted),
                                    ),
                                  ],
                                ),
                              ),
                              IconButton(
                                tooltip: 'Удалить чат',
                                onPressed: () => _delete(c),
                                icon: Icon(Icons.close_rounded, size: 20, color: p.muted),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// «Прикреплено: имя» над полем ввода, с крестиком.
class _AttachPreview extends StatelessWidget {
  final ChatAttachment? att;
  final String? note;
  final VoidCallback onClear;
  const _AttachPreview({required this.att, required this.note, required this.onClear});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final a = att;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, 0),
      child: Container(
        padding: const EdgeInsets.only(left: Space.m),
        decoration: BoxDecoration(
          color: p.card,
          borderRadius: BorderRadius.circular(Radii.chip),
          border: Border.all(color: a == null ? p.danger : p.line),
        ),
        child: Row(
          children: [
            Icon(
              a == null ? Icons.error_outline_rounded : (a.image ? Icons.image_outlined : Icons.description_outlined),
              size: 18,
              color: a == null ? p.danger : p.accent,
            ),
            const SizedBox(width: Space.s),
            Expanded(
              child: Text(
                a == null ? note! : 'прикреплено: ${a.name}',
                overflow: TextOverflow.ellipsis,
                style: s.body(13, color: a == null ? p.danger : p.text),
              ),
            ),
            IconButton(
              tooltip: 'Убрать',
              onPressed: onClear,
              icon: Icon(Icons.close_rounded, size: 18, color: p.muted),
            ),
          ],
        ),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  final ChatMsg m;
  final Api api;
  final ValueChanged<String> onChoose;
  const _Bubble({required this.m, required this.api, required this.onChoose});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    if (m.role == 'user') {
      final a = m.att;
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.8),
          margin: const EdgeInsets.fromLTRB(Space.xxl, Space.s, Space.l, Space.s),
          padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
          decoration: BoxDecoration(
            color: p.accent,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(Radii.tile),
              topRight: Radius.circular(Radii.tile),
              bottomLeft: Radius.circular(Radii.tile),
              bottomRight: Radius.circular(6),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              if (a != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(a.image ? Icons.image_outlined : Icons.description_outlined, size: 16, color: p.onAccent),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(
                          a.name,
                          overflow: TextOverflow.ellipsis,
                          style: s.body(13, weight: FontWeight.w600, color: p.onAccent),
                        ),
                      ),
                    ],
                  ),
                ),
              Text(m.content, style: s.body(15, color: p.onAccent)),
            ],
          ),
        ),
      );
    }
    final body = s.body(15, color: m.error ? p.danger : p.text);
    // поиск по смыслу: «Лекция 5 · слайд 12» → страница; одинаковые места — один чип
    final seen = <String>{};
    final pages = [
      for (final src in m.sources)
        if (src['page'] != null && seen.add('${src['id']}:${src['page']}')) src,
    ];
    final whole = [
      for (final src in m.sources)
        if (src['page'] == null) src,
    ];
    // «[1]», «[2]» в ответе — кнопками к тому же месту, что чипы под ответом
    final cites = {
      for (final src in m.sources)
        if (src['n'] is num) (src['n'] as num).toInt(): src,
    };
    InlineSpan? cite(int n) {
      final src = cites[n];
      if (src == null) return null;
      return WidgetSpan(
        alignment: PlaceholderAlignment.middle,
        child: _Cite(n: n, onTap: () => _openSource(context, src)),
      );
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.xl, Space.s, Space.xl, Space.s),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SelectionArea(
            child: m.html.isNotEmpty
                ? Text.rich(tgHtml(m.html, body, link: p.accent, codeBg: p.line, cite: cite))
                : (cites.isEmpty
                      ? Text(m.content, style: body)
                      : Text.rich(TextSpan(children: citeSpans(m.content, body, cite)))),
          ),
          if (m.choose.isNotEmpty) ...[
            const SizedBox(height: Space.s),
            Wrap(
              spacing: Space.s,
              runSpacing: Space.s,
              children: [
                for (final c in m.choose)
                  ActionChip(
                    backgroundColor: p.card,
                    side: BorderSide(color: p.accent),
                    shape: const StadiumBorder(),
                    // длинное название предмета — в две строки, а не обрезано
                    label: Text(c, softWrap: true, maxLines: 3, style: s.body(13, weight: FontWeight.w600)),
                    onPressed: () {
                      tick();
                      onChoose(c);
                    },
                  ),
              ],
            ),
          ],
          // «скинь лк 5 по …» — найденные файлы, нажал — лист файла
          if (m.files.isNotEmpty || pages.isNotEmpty || whole.isNotEmpty) ...[
            const SizedBox(height: Space.s),
            Wrap(
              spacing: Space.s,
              runSpacing: Space.s,
              children: [
                for (final f in m.files)
                  _chip(
                    context,
                    icon: Icons.insert_drive_file_outlined,
                    label: '${f['title']}',
                    onTap: () => showFileSheet(context, api, FileItem.fromJson(f)),
                  ),
                for (final src in pages.take(6))
                  _chip(
                    context,
                    icon: Icons.auto_stories_outlined,
                    label: '${src['label'] ?? src['title']}',
                    onTap: () => _openSource(context, src),
                  ),
                for (final src in whole.take(4))
                  _chip(
                    context,
                    icon: Icons.menu_book_outlined,
                    label: '${src['title']}',
                    onTap: () => showFileSheet(
                      context,
                      api,
                      FileItem.fromJson({'id': src['id'], 'title': src['title'], 'has_text': true}),
                    ),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  /// Источник ответа: страница лекции (есть номер страницы) или весь файл.
  void _openSource(BuildContext context, Map<String, dynamic> src) {
    tick();
    if (src['page'] != null) {
      showPageSheet(context, api, src['id'] as int, (src['page'] as num).toInt());
    } else {
      showFileSheet(context, api, FileItem.fromJson({'id': src['id'], 'title': src['title'], 'has_text': true}));
    }
  }

  Widget _chip(BuildContext context, {required IconData icon, required String label, required VoidCallback onTap}) {
    final s = AppStyle.of(context);
    final p = s.p;
    return ActionChip(
      backgroundColor: p.card,
      side: BorderSide(color: p.line),
      shape: const StadiumBorder(),
      avatar: Icon(icon, size: 16, color: p.accent),
      label: Text(
        label,
        overflow: TextOverflow.ellipsis,
        style: s.body(12, color: p.muted),
      ),
      onPressed: () {
        tick();
        onTap();
      },
    );
  }
}

/// «[1]» в ответе — маленькая кнопка с номером источника.
class _Cite extends StatelessWidget {
  final int n;
  final VoidCallback onTap;
  const _Cite({required this.n, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Semantics(
      button: true,
      label: 'Источник $n',
      excludeSemantics: true,
      child: GestureDetector(
        key: Key('cite:$n'),
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        // поле нажатия шире самой метки — по пальцу, а не по пикселю
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 2),
          child: Container(
            constraints: const BoxConstraints(minWidth: 20),
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
            decoration: BoxDecoration(
              color: p.accent.withValues(alpha: 0.16),
              borderRadius: BorderRadius.circular(Radii.pill),
            ),
            child: Text(
              '$n',
              textAlign: TextAlign.center,
              style: s.body(12, weight: FontWeight.w700, color: p.accent).copyWith(height: 1.2),
            ),
          ),
        ),
      ),
    );
  }
}

/// Пустой экран помощника: что он умеет и сколько вопросов осталось сегодня.
class _Intro extends StatelessWidget {
  final int? left;
  const _Intro({required this.left});

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    final n = left;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.l),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Отвечает по лекциям твоей группы: объяснит тему, решит задачу, скажет, где в лекции.',
            style: s.body(15, color: p.muted),
          ),
          if (n != null) ...[
            const SizedBox(height: Space.s),
            Row(
              children: [
                Icon(Icons.chat_bubble_outline_rounded, size: 16, color: n > 0 ? p.accent : p.warn),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    n > 0
                        ? 'Сегодня можно ещё $n ${plural(n, 'вопрос', 'вопроса', 'вопросов')}'
                        : 'На сегодня вопросы кончились — завтра можно снова',
                    style: s.body(14, weight: FontWeight.w600, color: n > 0 ? p.text : p.warn),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

/// Убирает клавиатуру жестом, как UIScrollView с keyboardDismissMode
/// .interactive в приложении Claude: палец, который вёл переписку, дошёл до
/// поля ввода [barKey] (дальше — клавиатура), или поле смахнули вниз.
/// Просто листать переписку можно — клавиатура остаётся. Слушает сырые
/// касания и не спорит с прокруткой и кнопками за жест.
class KeyboardDragDismiss extends StatefulWidget {
  final GlobalKey barKey;
  final Widget child;
  const KeyboardDragDismiss({super.key, required this.barKey, required this.child});

  /// Насколько смахнуть поле ввода вниз, чтобы клавиатура ушла.
  static const barSwipe = 24.0;

  @override
  State<KeyboardDragDismiss> createState() => _KeyboardDragDismissState();
}

class _KeyboardDragDismissState extends State<KeyboardDragDismiss> {
  double? _start;
  bool _fromBar = false, _done = false;

  double? _barTop() {
    final box = widget.barKey.currentContext?.findRenderObject();
    return box is RenderBox && box.hasSize ? box.localToGlobal(Offset.zero).dy : null;
  }

  void _hide() => FocusManager.instance.primaryFocus?.unfocus();

  void _move(PointerMoveEvent e) {
    final start = _start, top = _barTop();
    if (start == null || top == null || _done) return;
    final y = e.position.dy;
    final down = y - start;
    if (_fromBar ? down > KeyboardDragDismiss.barSwipe : (down > 0 && y >= top)) {
      _done = true;
      _hide();
    }
  }

  void _end() {
    // поле ввода берёт фокус по отпусканию пальца уже после нас (жесты
    // разбираются в конце события) — убираем ещё раз следом
    if (_done) scheduleMicrotask(_hide);
    _start = null;
    _done = false;
  }

  @override
  Widget build(BuildContext context) => Listener(
    onPointerDown: (e) {
      _start = e.position.dy;
      _done = false;
      final top = _barTop();
      _fromBar = top != null && e.position.dy >= top;
    },
    onPointerMove: _move,
    onPointerUp: (_) => _end(),
    onPointerCancel: (_) => _end(),
    child: widget.child,
  );
}

class _InputBar extends StatelessWidget {
  final TextEditingController controller;
  final bool busy;
  final VoidCallback onSend, onAttach;
  const _InputBar({
    super.key,
    required this.controller,
    required this.busy,
    required this.onSend,
    required this.onAttach,
  });

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, Space.m),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6),
        decoration: BoxDecoration(
          color: p.tabbar,
          borderRadius: BorderRadius.circular(Radii.tabbar),
          border: Border.all(color: p.line),
        ),
        child: Row(
          children: [
            IconButton(
              tooltip: 'Прикрепить фото или файл',
              onPressed: busy ? null : onAttach,
              icon: Icon(Icons.attach_file_rounded, color: p.muted),
            ),
            Expanded(
              child: TextField(
                controller: controller,
                minLines: 1,
                maxLines: 5,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => onSend(),
                style: s.body(15),
                decoration: InputDecoration(
                  border: InputBorder.none,
                  hintText: 'Спроси про лекцию или задачу',
                  hintStyle: s.body(15, color: p.muted),
                ),
              ),
            ),
            IconButton.filled(
              tooltip: 'Отправить',
              style: IconButton.styleFrom(backgroundColor: p.accent, foregroundColor: p.onAccent),
              onPressed: busy ? null : onSend,
              icon: const Icon(Icons.arrow_upward_rounded),
            ),
          ],
        ),
      ),
    );
  }
}
