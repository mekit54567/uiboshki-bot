// Карта корпусов (5.100.4, Никита 18.10): «Ещё → Карта», не вкладкой. Планы
// этажей, поиск аудитории и маршрут «отсюда → сюда» (считает сервер, /api/map).
// Данные — снимок карты Пульса РТУ МИРЭА; источник подписан внизу экрана.
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/api.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/capy.dart';
import '../widgets/capy_refresh.dart' show CapyLoading;
import '../widgets/common.dart';
import 'files.dart' show BackRow;

/// Аудитория на плане: контур в единицах плана.
class MapRoom {
  final String id, name, kind;
  final List<Offset> shape;
  const MapRoom({required this.id, required this.name, required this.kind, required this.shape});

  factory MapRoom.fromJson(Map j) => MapRoom(
    id: '${j['id']}',
    name: '${j['name']}',
    kind: '${j['kind'] ?? 'room'}',
    shape: [for (final p in j['shape'] as List) Offset((p[0] as num).toDouble(), (p[1] as num).toDouble())],
  );

  Rect get bounds => _bounds(shape);

  /// Точка внутри контура (луч вправо, чётность пересечений).
  bool contains(Offset q) {
    var inside = false;
    for (var i = 0, j = shape.length - 1; i < shape.length; j = i++) {
      final a = shape[i], b = shape[j];
      if ((a.dy > q.dy) != (b.dy > q.dy) && q.dx < (b.dx - a.dx) * (q.dy - a.dy) / (b.dy - a.dy) + a.dx) {
        inside = !inside;
      }
    }
    return inside;
  }
}

Rect _bounds(List<Offset> pts) {
  var r = Rect.fromLTRB(pts.first.dx, pts.first.dy, pts.first.dx, pts.first.dy);
  for (final p in pts) {
    r = r.expandToInclude(Rect.fromLTRB(p.dx, p.dy, p.dx, p.dy));
  }
  return r;
}

class MapFloor {
  final int n;
  final Size size;
  final List<Offset> outline;
  final List<MapRoom> rooms;
  const MapFloor({required this.n, required this.size, required this.outline, required this.rooms});

  factory MapFloor.fromJson(Map j) => MapFloor(
    n: j['n'] as int,
    size: Size((j['w'] as num).toDouble(), (j['h'] as num).toDouble()),
    outline: [for (final p in j['outline'] as List? ?? []) Offset((p[0] as num).toDouble(), (p[1] as num).toDouble())],
    rooms: [for (final r in j['rooms'] as List) MapRoom.fromJson(r as Map)],
  );

  MapRoom? roomAt(Offset q) => rooms.where((r) => r.contains(q)).firstOrNull;
}

/// Маршрут с сервера: куски по этажам и переходы между ними.
class MapRoute {
  final String fromName, toName;
  final int fromFloor, toFloor, meters, minutes;
  final Map<int, List<List<Offset>>> legs;
  final List<({String kind, int from, int to})> steps;
  const MapRoute({
    required this.fromName,
    required this.toName,
    required this.fromFloor,
    required this.toFloor,
    required this.meters,
    required this.minutes,
    required this.legs,
    required this.steps,
  });

  factory MapRoute.fromJson(Map j) {
    final legs = <int, List<List<Offset>>>{};
    for (final l in j['legs'] as List) {
      legs.putIfAbsent(l['floor'] as int, () => []).add([
        for (final p in l['points'] as List) Offset((p[0] as num).toDouble(), (p[1] as num).toDouble()),
      ]);
    }
    return MapRoute(
      fromName: '${j['from']['name']}',
      toName: '${j['to']['name']}',
      fromFloor: j['from']['floor'] as int,
      toFloor: j['to']['floor'] as int,
      meters: (j['meters'] as num).toInt(),
      minutes: (j['minutes'] as num).toInt(),
      legs: legs,
      steps: [for (final s in j['steps'] as List) (kind: '${s['kind']}', from: s['from'] as int, to: s['to'] as int)],
    );
  }

  /// «41 м · 1 мин · по лестнице на 3 этаж»
  String get summary {
    final parts = ['$meters м', '~$minutes мин'];
    for (final s in steps) {
      final how = s.kind == 'lift' ? 'на лифте' : 'по лестнице';
      parts.add('$how ${s.to > s.from ? 'на' : 'вниз на'} ${s.to} этаж');
    }
    return parts.join(' · ');
  }
}

class MapScreen extends StatefulWidget {
  final Api api;
  final VoidCallback? onUnauthorized;
  const MapScreen({super.key, required this.api, this.onUnauthorized});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  final _q = TextEditingController();
  final _view = TransformationController();
  final _plans = <String, Future<List<MapFloor>>>{};
  String? _campus;
  int? _floor;
  List _found = const [];
  int _ask = 0;

  /// Короткие имена корпусов («В-78») — в листе аудитории, если корпусов несколько.
  Map<String, String> _shorts = const {};

  /// Выбранные аудитории: (id, название, этаж).
  ({String id, String name, int floor})? _from, _to, _focus;
  MapRoute? _route;
  bool _lift = false;

  @override
  void dispose() {
    _q.dispose();
    _view.dispose();
    super.dispose();
  }

  Future<List<MapFloor>> _plan(String id) => _plans.putIfAbsent(
    id,
    () =>
        widget.api
            .get('/map/${Uri.encodeComponent(id)}')
            .then((j) => [for (final f in (j as Map)['floors'] as List) MapFloor.fromJson(f as Map)])
          ..catchError((Object e) {
            _plans.remove(id); // «Ещё раз» спросит заново
            throw e;
          }),
  );

  Future<void> _search(String q) async {
    final n = ++_ask;
    if (q.trim().isEmpty) {
      setState(() => _found = const []);
      return;
    }
    try {
      final j = await widget.api.get('/map/find?${Uri(queryParameters: {'q': q.trim()}).query}');
      if (mounted && n == _ask) setState(() => _found = (j as Map)['rooms'] as List? ?? const []);
    } catch (_) {}
  }

  void _show(Map hit) {
    FocusScope.of(context).unfocus();
    tick();
    final r = (id: '${hit['id']}', name: '${hit['name']}', floor: hit['floor'] as int);
    setState(() {
      _campus = '${hit['campus']}';
      _floor = r.floor;
      _focus = r;
      _q.clear();
      _found = const [];
      _whole();
    });
    _roomSheet(r);
  }

  Future<void> _roomSheet(({String id, String name, int floor}) r) async {
    final pick = await appSheet<String>(
      context,
      (c) => SheetFrame(
        key: const Key('map:room'),
        title: r.name,
        text: [if (_shorts.length > 1) ?_shorts[_campus], '${r.floor} этаж'].join(' · '),
        action: 'Сюда',
        cancel: 'Отсюда',
        onAction: () => Navigator.pop(c, 'to'),
        onCancel: () => Navigator.pop(c, 'from'),
      ),
    );
    if (pick == null || !mounted) return;
    setState(() {
      if (pick == 'to') _to = r;
      if (pick == 'from') _from = r;
      // та же аудитория и отсюда, и сюда — оставляем последнее
      if (_from != null && _from?.id == _to?.id) {
        if (pick == 'to') {
          _from = null;
        } else {
          _to = null;
        }
      }
      _route = null;
    });
    await _build();
  }

  Future<void> _build() async {
    final a = _from, b = _to, campus = _campus;
    if (a == null || b == null || campus == null) return;
    try {
      final j = await widget.api.get(
        '/map/route?${Uri(queryParameters: {'campus': campus, 'src': a.id, 'dst': b.id, if (_lift) 'lift': 'true'}).query}',
      );
      if (!mounted || _from != a || _to != b) return;
      setState(() {
        _route = MapRoute.fromJson(j as Map);
        _floor = _route!.fromFloor;
        _whole();
      });
    } catch (_) {
      if (mounted) showToast(context, 'Маршрут не построился', kind: ToastKind.error);
    }
  }

  /// Этаж целиком и по центру окна (робот 18.10: после приближения корпус
  /// уезжал вниз, а план срезался сбоку) — после поиска, маршрута, смены
  /// этажа или корпуса. Ближе — пальцами.
  void _whole() => _view.value = Matrix4.identity();

  void _clear() {
    tick();
    setState(() {
      _from = _to = _focus = null;
      _route = null;
    });
  }

  void _tap(MapFloor f, Offset at) {
    final room = f.roomAt(at);
    if (room == null) return;
    tick();
    final r = (id: room.id, name: room.name, floor: f.n);
    setState(() => _focus = r);
    _roomSheet(r);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Backdrop(
        child: SafeArea(
          bottom: false,
          child: Loader<List>(
            load: () async => (await widget.api.get('/map'))['campuses'] as List? ?? const [],
            onUnauthorized: widget.onUnauthorized,
            builder: (context, campuses, _) => _body(context, campuses),
          ),
        ),
      ),
    );
  }

  Widget _body(BuildContext context, List campuses) {
    final s = AppStyle.of(context);
    final p = s.p;
    if (campuses.isEmpty) {
      return const Column(
        children: [
          BackRow(),
          Notice(title: 'Карты пока нет', text: 'Скоро появится', pose: CapyPose.sad),
        ],
      );
    }
    final campus = (campuses.where((c) => c['id'] == _campus).firstOrNull ?? campuses.first) as Map;
    _campus = '${campus['id']}';
    _shorts = {for (final c in campuses) '${c['id']}': '${c['short'] ?? c['name']}'};
    final floors = [for (final f in campus['floors'] as List) f as int];
    final floor = floors.contains(_floor) ? _floor! : floors.first;
    Widget chip(String text, bool on, VoidCallback tap, Key k, {bool dot = false}) => GestureDetector(
      key: k,
      onTap: () {
        tick();
        tap();
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        decoration: BoxDecoration(
          color: on ? p.accent : p.card,
          borderRadius: BorderRadius.circular(Radii.chip),
          border: Border.all(color: on ? p.accent : p.line),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              text,
              style: s.body(14, weight: FontWeight.w600, color: on ? p.onAccent : p.text),
            ),
            if (dot) ...[
              const SizedBox(width: 6),
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(color: on ? p.onAccent : p.accent, shape: BoxShape.circle),
              ),
            ],
          ],
        ),
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const BackRow(),
        const ScreenTitle(title: 'Карта'),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.l),
          child: TextField(
            key: const Key('map:search'),
            controller: _q,
            onChanged: _search,
            textInputAction: TextInputAction.search,
            style: s.body(17, weight: FontWeight.w600),
            decoration: InputDecoration(
              hintText: 'Аудитория, например А-223',
              hintStyle: s.body(17, color: p.muted),
              prefixIcon: Icon(Icons.search_rounded, color: p.muted),
              suffixIcon: _q.text.isEmpty
                  ? null
                  : IconButton(
                      tooltip: 'Очистить',
                      icon: Icon(Icons.close_rounded, color: p.muted),
                      onPressed: () {
                        _q.clear();
                        _search('');
                      },
                    ),
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
        if (_found.isNotEmpty)
          Expanded(
            child: ListView(
              key: const Key('map:found'),
              padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, Space.xxl),
              children: [
                for (final h in _found)
                  Padding(
                    padding: const EdgeInsets.only(bottom: Space.s),
                    child: Tile(
                      key: Key('map:hit:${h['id']}'),
                      onTap: () => _show(h as Map),
                      padding: const EdgeInsets.symmetric(horizontal: Space.l, vertical: Space.m),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text('${h['name']}', style: s.body(16, weight: FontWeight.w700)),
                          ),
                          Text(
                            [
                              if ('${h['short'] ?? ''}'.isNotEmpty && campuses.length > 1) '${h['short']}',
                              '${h['floor']} этаж',
                            ].join(' · '),
                            style: s.body(14, color: p.muted),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          )
        else ...[
          const SizedBox(height: Space.m),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: Space.l),
            child: Row(
              children: [
                if (campuses.length > 1) ...[
                  for (final c in campuses)
                    Padding(
                      padding: const EdgeInsets.only(right: Space.s),
                      child: chip(
                        '${c['short'] ?? c['name']}',
                        c['id'] == _campus,
                        () => setState(() {
                          _campus = '${c['id']}';
                          _floor = null;
                          _from = _to = _focus = null;
                          _route = null;
                          _whole();
                        }),
                        Key('map:campus:${c['id']}'),
                      ),
                    ),
                  Container(
                    width: 1,
                    height: 24,
                    color: p.line,
                    margin: const EdgeInsets.only(right: Space.s),
                  ),
                ],
                for (final n in floors)
                  Padding(
                    padding: const EdgeInsets.only(right: Space.s),
                    child: chip(
                      '$n этаж',
                      n == floor,
                      () => setState(() {
                        _floor = n;
                        _whole();
                      }),
                      Key('map:floor:$n'),
                      dot: _route?.legs.containsKey(n) ?? false,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: Space.m),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: Space.l),
              child: FutureBuilder<List<MapFloor>>(
                key: ValueKey(_campus),
                future: _plan(_campus!),
                builder: (context, snap) {
                  if (snap.hasError) {
                    return Notice(
                      title: 'Не загрузилось',
                      text: 'План корпуса не получилось загрузить',
                      onRetry: () => setState(() {}),
                      pose: CapyPose.sad,
                    );
                  }
                  if (!snap.hasData) return const Center(child: CapyLoading());
                  final f = snap.data!.where((f) => f.n == floor).firstOrNull;
                  if (f == null) return const SizedBox.shrink();
                  return Tile(
                    key: const Key('map:plan'),
                    padding: EdgeInsets.zero,
                    child: LayoutBuilder(
                      builder: (context, box) {
                        final size = Size(box.maxWidth, box.maxHeight);
                        final fit = _Fit(f.size, size);
                        return InteractiveViewer(
                          transformationController: _view,
                          minScale: 1,
                          maxScale: 6,
                          child: GestureDetector(
                            onTapUp: (d) => _tap(f, fit.toPlan(d.localPosition)),
                            child: CustomPaint(
                              size: size,
                              painter: _FloorPainter(
                                floor: f,
                                fit: fit,
                                p: p,
                                font: s.body(12).fontFamily,
                                marked: {
                                  for (final r in [_from, _to, _focus])
                                    if (r != null) r.id,
                                },
                                route: _route?.legs[f.n] ?? const [],
                                start: _route != null && _route!.fromFloor == f.n,
                                end: _route != null && _route!.toFloor == f.n,
                              ),
                            ),
                          ),
                        );
                      },
                    ),
                  );
                },
              ),
            ),
          ),
          _RouteBar(
            from: _from?.name,
            to: _to?.name,
            route: _route,
            lift: _lift,
            onLift: () {
              tick();
              setState(() => _lift = !_lift);
              _build();
            },
            onClear: _clear,
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(Space.l, Space.s, Space.l, Space.m + MediaQuery.paddingOf(context).bottom),
            child: Text(
              'Карта: ${campus['source'] ?? 'Пульс РТУ МИРЭА'}',
              key: const Key('map:source'),
              textAlign: TextAlign.center,
              style: s.body(12, color: p.muted),
            ),
          ),
        ],
      ],
    );
  }
}

/// Отсюда/сюда и что получилось: «Т-101 → Т-305», длина и переходы.
class _RouteBar extends StatelessWidget {
  final String? from, to;
  final MapRoute? route;
  final bool lift;
  final VoidCallback onLift, onClear;
  const _RouteBar({
    required this.from,
    required this.to,
    required this.route,
    required this.lift,
    required this.onLift,
    required this.onClear,
  });

  @override
  Widget build(BuildContext context) {
    if (from == null && to == null) {
      final s = AppStyle.of(context);
      return Padding(
        padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, 0),
        child: Text(
          'Нажми на аудиторию, чтобы построить маршрут',
          textAlign: TextAlign.center,
          style: s.body(14, color: s.p.muted),
        ),
      );
    }
    final s = AppStyle.of(context);
    final p = s.p;
    final r = route;
    final floors = r != null && r.steps.isNotEmpty;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.l, 0),
      child: Tile(
        key: const Key('map:route'),
        padding: const EdgeInsets.fromLTRB(Space.l, Space.m, Space.s, Space.m),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${from ?? 'Откуда?'}  →  ${to ?? 'Куда?'}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: s.body(16, weight: FontWeight.w700),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    r?.summary ?? (from == null ? 'Выбери, откуда идёшь' : 'Выбери, куда идёшь'),
                    style: s.body(13, color: p.muted),
                  ),
                ],
              ),
            ),
            if (floors)
              IconButton(
                key: const Key('map:lift'),
                tooltip: lift ? 'По лестнице' : 'На лифте',
                onPressed: onLift,
                icon: Icon(lift ? Icons.elevator_outlined : Icons.stairs_outlined, color: p.accent),
              ),
            IconButton(
              key: const Key('map:route:clear'),
              tooltip: 'Сбросить',
              onPressed: onClear,
              icon: Icon(Icons.close_rounded, color: p.muted),
            ),
          ],
        ),
      ),
    );
  }
}

/// План в окне: масштаб и сдвиг, чтобы этаж целиком влез по центру.
class _Fit {
  final double scale;
  final Offset shift;
  _Fit._(this.scale, this.shift);

  factory _Fit(Size plan, Size box) {
    const pad = 12.0;
    final k = math.min((box.width - pad * 2) / plan.width, (box.height - pad * 2) / plan.height);
    return _Fit._(k, Offset((box.width - plan.width * k) / 2, (box.height - plan.height * k) / 2));
  }

  Offset toPlan(Offset local) => (local - shift) / scale;
}

class _FloorPainter extends CustomPainter {
  final MapFloor floor;
  final _Fit fit;
  final Palette p;
  final String? font;
  final Set<String> marked;
  final List<List<Offset>> route;
  final bool start, end;
  _FloorPainter({
    required this.floor,
    required this.fit,
    required this.p,
    required this.font,
    required this.marked,
    required this.route,
    required this.start,
    required this.end,
  });

  Color _fill(String kind) => switch (kind) {
    'wc' => p.ok.withValues(alpha: 0.18),
    'food' => p.warn.withValues(alpha: 0.22),
    'stairs' || 'lift' => p.muted.withValues(alpha: 0.22),
    'entrance' => p.ok.withValues(alpha: 0.28),
    _ => p.text.withValues(alpha: 0.06),
  };

  Path _path(List<Offset> pts) => Path()..addPolygon(pts, true);

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.translate(fit.shift.dx, fit.shift.dy);
    canvas.scale(fit.scale);
    final line = 1.2 / fit.scale;
    if (floor.outline.length >= 3) {
      canvas.drawPath(_path(floor.outline), Paint()..color = p.text.withValues(alpha: 0.04));
      canvas.drawPath(
        _path(floor.outline),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = line * 1.6
          ..color = p.line,
      );
    }
    for (final r in floor.rooms) {
      final on = marked.contains(r.id);
      canvas.drawPath(_path(r.shape), Paint()..color = on ? p.accent.withValues(alpha: 0.5) : _fill(r.kind));
      canvas.drawPath(
        _path(r.shape),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = on ? line * 2 : line
          ..color = on ? p.accent : p.line,
      );
      _label(canvas, r, on);
    }
    if (route.isNotEmpty) {
      final stroke = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 4 / fit.scale
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round
        ..color = p.accent;
      for (final leg in route) {
        if (leg.length > 1) canvas.drawPath(Path()..addPolygon(leg, false), stroke);
      }
      final dot = 6 / fit.scale;
      final ring = Paint()..color = p.cardSolid;
      void mark(Offset at, Color c) {
        canvas.drawCircle(at, dot + 2 / fit.scale, ring);
        canvas.drawCircle(at, dot, Paint()..color = c);
      }

      // начало — зелёная точка, конец — красная, переход на другой этаж — кольцо
      void transfer(Offset at) {
        canvas.drawCircle(at, dot + 2 / fit.scale, ring);
        canvas.drawCircle(
          at,
          dot - 1 / fit.scale,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 3 / fit.scale
            ..color = p.accent,
        );
      }

      start ? mark(route.first.first, p.ok) : transfer(route.first.first);
      end ? mark(route.last.last, p.danger) : transfer(route.last.last);
    }
    canvas.restore();
  }

  void _label(Canvas canvas, MapRoom r, bool on) {
    final b = r.bounds;
    final text = switch (r.kind) {
      'stairs' => 'Лестница',
      'lift' => 'Лифт',
      _ => r.name,
    };
    // шрифт — по комнате, но не крупнее 15 точек на экране
    final size = math.min(math.min(b.width / (text.length * 0.62 + 1), b.height * 0.32), 15 / fit.scale);
    if (size * fit.scale < 6) return; // мельче не прочесть — подпись видна при увеличении
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          fontFamily: font,
          fontSize: size,
          fontWeight: on ? FontWeight.w800 : FontWeight.w600,
          color: on ? p.text : p.text.withValues(alpha: 0.8),
        ),
      ),
      textDirection: TextDirection.ltr,
      maxLines: 1,
    )..layout(maxWidth: b.width);
    tp.paint(canvas, b.center - Offset(tp.width / 2, tp.height / 2));
    tp.dispose();
  }

  @override
  bool shouldRepaint(_FloorPainter old) =>
      old.floor != floor ||
      old.fit.scale != fit.scale ||
      old.p != p ||
      old.marked.length != marked.length ||
      !old.marked.containsAll(marked) ||
      old.route != route;
}
