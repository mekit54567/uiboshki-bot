// «Из какой ты группы?» — поиск по справочнику групп МИРЭА (как лист в
// WebApp и /group в боте). Без группы приложение не показывает данные:
// расписание, сроки и файлы у каждой группы свои (этап 1). Из «Ещё →
// Группа» — сверху «Сейчас: УИБО-03-24», под поиском «Я староста этой
// группы» (владелец, 2.7).
import 'dart:async';

import 'package:flutter/material.dart';

import '../api/api.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/common.dart';

class GroupPickScreen extends StatefulWidget {
  final Api api;

  /// true — первый вход, без группы дальше нельзя (нет «назад»).
  final bool required;
  const GroupPickScreen({super.key, required this.api, this.required = false});

  @override
  State<GroupPickScreen> createState() => _GroupPickScreenState();
}

class _GroupPickScreenState extends State<GroupPickScreen> {
  final _q = TextEditingController();
  Timer? _debounce;
  List<Map<String, dynamic>> _items = [];
  String? _note;
  int _seq = 0;

  /// Текущая группа из /me (только не при первом выборе).
  Map<String, dynamic>? _current;
  String? _adminNote;

  @override
  void initState() {
    super.initState();
    if (!widget.required) _loadCurrent();
  }

  Future<void> _loadCurrent() async {
    try {
      final me = await widget.api.get('/me');
      final g = me is Map ? me['group'] : null;
      if (g is Map && mounted) setState(() => _current = Map<String, dynamic>.from(g));
    } catch (_) {} // нет сети — просто без строки «Сейчас»
  }

  /// «Я староста этой группы» — запрос владельцу бота, ответ придёт в бота.
  Future<void> _askAdmin() async {
    tick();
    try {
      await widget.api.post('/me/group/admin');
      if (mounted) setState(() => _adminNote = 'Запрос отправлен — ответ придёт в бота.');
    } on ApiError catch (e) {
      if (mounted) setState(() => _adminNote = e.message);
    } catch (e) {
      if (mounted) setState(() => _adminNote = errorText(e));
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _q.dispose();
    super.dispose();
  }

  void _changed(String text) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () => _search(text));
  }

  Future<void> _search(String text) async {
    final my = ++_seq; // ответ на старый запрос не перетирает новый
    if (text.trim().length < 2) {
      setState(() => _items = []);
      return;
    }
    try {
      final r = await widget.api.get('/groups/search?q=${Uri.encodeQueryComponent(text.trim())}');
      if (my != _seq || !mounted) return;
      setState(() {
        _items = [for (final g in r['items'] as List) Map<String, dynamic>.from(g)];
        _note = _items.isEmpty ? 'Такой группы не нашёл — проверь, как написано: «УИБО-03-24» (можно и латиницей: UIBO-03-24).' : null;
      });
    } catch (e) {
      if (mounted) setState(() => _note = errorText(e));
    }
  }

  Future<void> _choose(Map<String, dynamic> g) async {
    tick();
    try {
      final r = await widget.api.post('/me/group', {'id': g['id']});
      if (mounted) Navigator.pop(context, Map<String, dynamic>.from(r['group']));
    } on ApiError catch (e) {
      setState(() => _note = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStyle.of(context);
    final p = s.p;
    return PopScope(
      canPop: !widget.required,
      child: Scaffold(
        body: Backdrop(
          child: SafeArea(
            child: ListView(
              padding: const EdgeInsets.only(bottom: Space.xxl),
              children: [
                if (!widget.required)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Padding(
                      padding: const EdgeInsets.only(left: Space.s),
                      child: IconButton(
                        tooltip: 'Назад',
                        onPressed: () => Navigator.pop(context),
                        icon: Icon(Icons.arrow_back_ios_new_rounded, size: 20, color: p.text),
                      ),
                    ),
                  )
                else
                  const SizedBox(height: Space.xl),
                const ScreenTitle(title: 'Из какой ты группы?'),
                if (_current != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.m),
                    child: Text.rich(
                      TextSpan(
                        children: [
                          const TextSpan(text: 'Сейчас: '),
                          TextSpan(
                            text: '${_current!['name']}',
                            style: s.body(17, weight: FontWeight.w700),
                          ),
                        ],
                      ),
                      key: const Key('group:current'),
                      style: s.body(17, color: p.muted),
                    ),
                  ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.l),
                  child: TextField(
                    controller: _q,
                    autofocus: true,
                    onChanged: _changed,
                    textCapitalization: TextCapitalization.characters,
                    style: s.body(17, weight: FontWeight.w600),
                    decoration: InputDecoration(
                      hintText: 'Например, УИБО-03-24',
                      hintStyle: s.body(17, color: p.muted),
                      prefixIcon: Icon(Icons.search_rounded, color: p.muted),
                      filled: true,
                      fillColor: p.card,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(Radii.tile),
                        borderSide: BorderSide(color: p.line),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(Radii.tile),
                        borderSide: BorderSide(color: p.line),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: Space.m),
                for (final g in _items)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(Space.l, 0, Space.l, Space.s),
                    child: Tile(
                      onTap: () => _choose(g),
                      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
                      child: Row(
                        children: [
                          Icon(Icons.groups_outlined, color: p.accent),
                          const SizedBox(width: Space.m),
                          Expanded(
                            child: Text('${g['name']}', style: s.body(16, weight: FontWeight.w600)),
                          ),
                          Icon(Icons.chevron_right_rounded, color: p.muted),
                        ],
                      ),
                    ),
                  ),
                if (_note != null)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.xl, vertical: Space.s),
                    child: Text(_note!, style: s.body(14, color: p.muted)),
                  ),
                // своей группой у бота заведует владелец — там просить нечего
                if (_current != null && _current!['own'] != true)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, 0),
                    child: Tile(
                      onTap: _adminNote == null ? _askAdmin : null,
                      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
                      child: Row(
                        children: [
                          Icon(Icons.verified_user_outlined, color: p.accent),
                          const SizedBox(width: Space.m),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('Я староста этой группы', style: s.body(16, weight: FontWeight.w600)),
                                Text(
                                  _adminNote ?? 'спрошу владельца бота — сможешь вести общие сроки и ДЗ',
                                  style: s.body(13, color: p.muted),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
