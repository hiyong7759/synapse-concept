import '../kiwi/kiwi_wasm.dart';
import '../kiwi/tokens.dart';

/// Result of [DateNormalizer.normalize].
class DateNormalizeResult {
  const DateNormalizeResult({
    required this.text,
    required this.splitNodes,
  });

  /// Input rewritten with deictic Korean date adverbs replaced by absolute
  /// Korean dates (e.g. "어제" → "2026년 4월 25일"). Recurrence-marked
  /// clauses are left untouched.
  final String text;

  /// Date components extracted as graph-node candidates. Each absolute date
  /// contributes its year/month/day pieces plus the full string, so callers
  /// can upsert all of them into `nodes` and tag with TIM.* categories.
  /// Order: year-level first, then month, day, full date.
  final List<String> splitNodes;
}

/// Deterministic Korean date normaliser.
///
/// Replaces save-pronoun (LLM) for the cases that v22 note input actually
/// uses — concrete deictic phrases ("어제"·"내일"·"이번 주 금요일") and ISO
/// dates. Modal phrases ("저번 주" 단독·"새벽"·"주말") and recurrence
/// expressions ("매주 금요일") are left intact: the former are too vague
/// to commit to a single date, the latter would lose meaning.
///
/// Algorithm:
///   1. Tokenize via [KiwiBackend].
///   2. Split into clauses on EF (sentence-final endings), EC (connective
///      endings of any kind), and strong conjunctions ("그리고"·"하지만"·…).
///   3. For each clause, check whether any recurrence marker is present.
///      If so, the entire clause is left untouched.
///   4. Otherwise, replace deictic date adverbs and ISO patterns with
///      absolute Korean dates and emit split-node candidates.
///
/// See docs/DESIGN_PIPELINE.md §의미 처리 파이프라인 (단일 경로).
class DateNormalizer {
  const DateNormalizer();

  Future<DateNormalizeResult> normalize(
    String text, {
    required KiwiBackend kiwi,
    required DateTime reference,
  }) async {
    if (text.isEmpty) {
      return const DateNormalizeResult(text: '', splitNodes: []);
    }

    final tokens = await kiwi.tokenize(text);
    final clauses = _splitClauses(text, tokens);

    final buffer = StringBuffer();
    final splitNodes = <String>[];
    var cursor = 0;

    for (final clause in clauses) {
      // Emit any whitespace / punctuation between the previous clause end
      // and this clause start verbatim.
      if (clause.start > cursor) {
        buffer.write(text.substring(cursor, clause.start));
      }
      final body = text.substring(clause.start, clause.end);
      if (_hasRecurrenceMarker(body)) {
        buffer.write(body);
      } else {
        final replaced = _rewriteClause(body, reference, splitNodes);
        buffer.write(replaced);
      }
      cursor = clause.end;
    }
    if (cursor < text.length) {
      buffer.write(text.substring(cursor));
    }

    return DateNormalizeResult(
      text: buffer.toString(),
      splitNodes: splitNodes,
    );
  }

  // ── clause split ─────────────────────────────────────────

  List<_Clause> _splitClauses(String text, List<KiwiToken> tokens) {
    final boundaries = <int>[];
    for (final t in tokens) {
      final tag = t.tag;
      final isBoundary = tag == 'EF' ||
          tag == 'EC' ||
          (tag == 'MAJ' && _strongConjunctions.contains(t.surface)) ||
          (tag == 'MAG' && _strongConjunctions.contains(t.surface));
      if (isBoundary) {
        boundaries.add(t.start + t.length);
      }
    }
    final clauses = <_Clause>[];
    var start = 0;
    for (final b in boundaries) {
      if (b <= start) continue;
      clauses.add(_Clause(start, b));
      start = b;
    }
    if (start < text.length) {
      clauses.add(_Clause(start, text.length));
    }
    if (clauses.isEmpty) clauses.add(_Clause(0, text.length));
    return clauses;
  }

  // ── recurrence detection ─────────────────────────────────

  bool _hasRecurrenceMarker(String body) {
    for (final m in _recurrenceMarkers) {
      if (body.contains(m)) return true;
    }
    if (_perNUnitRegex.hasMatch(body)) return true;
    return false;
  }

  // ── deictic rewrite ──────────────────────────────────────

  String _rewriteClause(
    String body,
    DateTime reference,
    List<String> splitNodes,
  ) {
    var out = body;
    out = _rewriteIsoDates(out, splitNodes);
    out = _rewriteRelativeDays(out, reference, splitNodes);
    out = _rewriteRelativeWeekdays(out, reference, splitNodes);
    return out;
  }

  String _rewriteIsoDates(String body, List<String> splitNodes) {
    return body.replaceAllMapped(_isoDateRegex, (m) {
      final y = int.parse(m.group(1)!);
      final mo = int.parse(m.group(2)!);
      final dRaw = m.group(3);
      if (dRaw == null) {
        final out = '$y년 $mo월';
        _emitSplitNodes(splitNodes, year: y, month: mo);
        return out;
      }
      final d = int.parse(dRaw);
      final out = '$y년 $mo월 $d일';
      _emitSplitNodes(splitNodes, year: y, month: mo, day: d);
      return out;
    });
  }

  String _rewriteRelativeDays(
    String body,
    DateTime reference,
    List<String> splitNodes,
  ) {
    return body.replaceAllMapped(_relativeDayRegex, (m) {
      final word = m.group(0)!;
      final offset = _relativeDayOffsets[word]!;
      final d = reference.add(Duration(days: offset));
      _emitSplitNodes(splitNodes,
          year: d.year, month: d.month, day: d.day);
      return '${d.year}년 ${d.month}월 ${d.day}일';
    });
  }

  String _rewriteRelativeWeekdays(
    String body,
    DateTime reference,
    List<String> splitNodes,
  ) {
    return body.replaceAllMapped(_relativeWeekdayRegex, (m) {
      final whichWeek = m.group(1)!; // 이번 / 지난 / 다음
      final weekday = m.group(2)!;   // 월~일
      final weekOffset = switch (whichWeek) {
        '이번' => 0,
        '지난' || '저번' => -1,
        '다음' => 1,
        _ => 0,
      };
      final targetDow = _weekdayIndex[weekday]!;
      final base = reference.add(Duration(days: 7 * weekOffset));
      // Anchor on the ISO week's Monday so "이번 주 금요일" lands on the
      // Friday of the same Mon–Sun span as `base`, not 7 days later.
      final monday = base.subtract(Duration(days: base.weekday - 1));
      final d = monday.add(Duration(days: targetDow - 1));
      _emitSplitNodes(splitNodes,
          year: d.year, month: d.month, day: d.day);
      return '${d.year}년 ${d.month}월 ${d.day}일';
    });
  }

  void _emitSplitNodes(
    List<String> bag, {
    required int year,
    required int month,
    int? day,
  }) {
    final yearStr = '$year년';
    final monthStr = '$month월';
    if (!bag.contains(yearStr)) bag.add(yearStr);
    if (!bag.contains(monthStr)) bag.add(monthStr);
    if (day != null) {
      final dayStr = '$day일';
      final fullStr = '$year년 $month월 $day일';
      if (!bag.contains(dayStr)) bag.add(dayStr);
      if (!bag.contains(fullStr)) bag.add(fullStr);
    } else {
      final partial = '$year년 $month월';
      if (!bag.contains(partial)) bag.add(partial);
    }
  }
}

class _Clause {
  const _Clause(this.start, this.end);
  final int start;
  final int end;
}

// ── word lists ───────────────────────────────────────────

const Set<String> _strongConjunctions = {
  '그리고', '하지만', '그러나', '그런데', '근데',
  '또는', '또', '그래도', '반면', '한편',
};

/// Recurrence markers. All entries are ≥2 jamo so substring matching does
/// not collide with deictic words ("오늘" 의 "늘" 같은 단음절 단어 충돌 방지
/// — 단음절 빈도 부사는 "항상"·"언제나"·"자주" 로 충분히 커버됨).
const Set<String> _recurrenceMarkers = {
  // 매-
  '매일', '매주', '매월', '매달', '매년', '매해', '매번', '매주말',
  // 격-
  '격일', '격주', '격월', '격년',
  // -마다
  '주마다', '월마다', '달마다', '해마다', '날마다',
  // 빈도 부사
  '항상', '언제나', '자주', '가끔', '종종', '때때로', '이따금', '수시로',
  // 주기성 키워드
  '정기적', '주기적', '꾸준히',
};

/// "N일마다 / N주마다 / N개월마다 / N년마다 / N달마다" 패턴.
final RegExp _perNUnitRegex = RegExp(r'\d+\s*(?:일|주|개월|달|년|해)\s*마다');

const Map<String, int> _relativeDayOffsets = {
  '그저께': -2,
  '엊그제': -2,
  '어제': -1,
  '오늘': 0,
  '내일': 1,
  '모레': 2,
  '글피': 3,
  '그글피': 4,
};

/// Single regex with longest-prefix-first alternation so "그글피" wins over
/// "글피" and the substring of "오늘" doesn't get clipped.
final RegExp _relativeDayRegex = RegExp(
  r'그글피|그저께|엊그제|모레|글피|어제|오늘|내일',
);

const Map<String, int> _weekdayIndex = {
  '월요일': DateTime.monday,
  '화요일': DateTime.tuesday,
  '수요일': DateTime.wednesday,
  '목요일': DateTime.thursday,
  '금요일': DateTime.friday,
  '토요일': DateTime.saturday,
  '일요일': DateTime.sunday,
};

/// "이번 / 지난 / 저번 / 다음 주 X요일" — 단독 X요일은 모호하므로 제외.
final RegExp _relativeWeekdayRegex = RegExp(
  r'(이번|지난|저번|다음)\s*주\s*(월요일|화요일|수요일|목요일|금요일|토요일|일요일)',
);

/// ISO date patterns: 2026-04-26, 2026.04.26, 2026/04/26, plus YYYY-MM
/// (no day) variants. Day group is optional via the `(?:[-./]\d{1,2})?`
/// trailing chunk; missing day → year+month rewrite.
final RegExp _isoDateRegex = RegExp(
  r'(\d{4})[-./](\d{1,2})(?:[-./](\d{1,2}))?',
);
