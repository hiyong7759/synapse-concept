// 19 대분류 + 114 소분류 시드 + 인접 맵 페어 + 인칭대명사 11 별칭.
// Single source: docs/DESIGN_CATEGORY.md §분류체계 + §인접 맵 + DESIGN_PIPELINE.md
// §자동 시드 예외 (`_FIRST_PERSON_ALIASES`).
//
// Seed roots and their subcategories are inserted into `categories` at v1
// migration time. Subcategory codes (e.g. "BOD.disease") are assembled by the
// application layer; the table itself only stores `(name, parent_id)`.

/// First-person aliases auto-seeded onto a `"나"` node at migration time so
/// "내가/저는/제가/..." all collapse onto the same node via `aliases`
/// lookup. Mirrors `engine/save.py:_FIRST_PERSON_ALIASES` (deduped to 11).
const List<String> firstPersonAliases = [
  '내', '저', '제', '나의', '저의', '제가',
  '나는', '저는', '내가', '나한테', '저한테',
];

/// One macro category root with its subcategory leaves.
class CategorySeedRoot {
  const CategorySeedRoot({
    required this.code,
    required this.title,
    required this.subs,
  });

  /// 3-letter macro code, also stored as the row's `name`. e.g. "PER".
  final String code;

  /// Human-readable title (Korean). Reference only — not stored in DB.
  final String title;

  /// Subcategory leaf names. Stored as child rows under this root.
  final List<String> subs;
}

/// 19-macro seed defined in DESIGN_CATEGORY §분류체계.
/// Total rows after seed = 19 roots + 114 leaves = 133.
const List<CategorySeedRoot> seedRoots19 = [
  CategorySeedRoot(code: 'PER', title: '사람', subs: [
    'individual', 'family', 'friend', 'colleague', 'public', 'org',
  ]),
  CategorySeedRoot(code: 'BOD', title: '신체·건강', subs: [
    'part', 'disease', 'medical', 'exercise', 'nutrition', 'sleep',
  ]),
  CategorySeedRoot(code: 'MND', title: '심리·감정', subs: [
    'emotion', 'personality', 'mental', 'motivation', 'coping',
  ]),
  CategorySeedRoot(code: 'FOD', title: '음식·요리', subs: [
    'ingredient', 'recipe', 'restaurant', 'drink', 'product',
  ]),
  CategorySeedRoot(code: 'LIV', title: '주거·생활', subs: [
    'housing', 'appliance', 'interior', 'supply', 'maintenance', 'moving',
  ]),
  CategorySeedRoot(code: 'MON', title: '돈·경제', subs: [
    'income', 'spending', 'invest', 'payment', 'loan', 'insurance',
  ]),
  CategorySeedRoot(code: 'WRK', title: '일·커리어', subs: [
    'workplace', 'role', 'jobchange', 'business', 'cert', 'tool',
  ]),
  CategorySeedRoot(code: 'TEC', title: '기술·디지털', subs: [
    'sw', 'hw', 'ai', 'infra', 'data', 'security',
  ]),
  CategorySeedRoot(code: 'EDU', title: '배움·지식', subs: [
    'school', 'online', 'language', 'academic', 'reading', 'exam',
  ]),
  CategorySeedRoot(code: 'LAW', title: '법·제도', subs: [
    'statute', 'contract', 'admin', 'rights', 'tax',
  ]),
  CategorySeedRoot(code: 'TRV', title: '이동·여행', subs: [
    'domestic', 'abroad', 'transport', 'stay', 'flight', 'place',
  ]),
  CategorySeedRoot(code: 'NAT', title: '자연·환경', subs: [
    'animal', 'plant', 'weather', 'terrain', 'ecology', 'space',
  ]),
  CategorySeedRoot(code: 'CUL', title: '문화·예술', subs: [
    'film', 'music', 'book', 'art', 'show', 'media',
  ]),
  CategorySeedRoot(code: 'HOB', title: '여가·취미', subs: [
    'sport', 'outdoor', 'game', 'craft', 'sing', 'collect', 'social',
  ]),
  CategorySeedRoot(code: 'SOC', title: '사회·시사', subs: [
    'politics', 'international', 'incident', 'economy', 'issue', 'news',
  ]),
  CategorySeedRoot(code: 'REL', title: '관계·소통', subs: [
    'romance', 'conflict', 'comm', 'manner', 'online',
  ]),
  CategorySeedRoot(code: 'REG', title: '종교·신앙', subs: [
    'christianity', 'buddhism', 'catholic', 'islam', 'other', 'practice',
  ]),
  CategorySeedRoot(code: 'TIM', title: '시간', subs: [
    'year', 'month', 'day', 'date', 'time', 'relative', 'period',
  ]),
  CategorySeedRoot(code: 'ACT', title: '행동·동작', subs: [
    'eat', 'move', 'use', 'make', 'talk', 'think', 'rest', 'work',
  ]),
];

/// Adjacency pairs at the subcategory level, single direction.
/// Code expands to bidirectional via [buildAdjacentMap].
/// Mirrors `_ADJACENT_PAIRS` in docs/DESIGN_CATEGORY.md §코드 표현
/// (kept Python ↔ Dart in sync — same edge list).
const List<(String, String)> seedAdjacentPairs = [
  // BOD
  ('BOD.disease', 'MND.mental'),
  ('BOD.sleep', 'MND.mental'),
  ('BOD.sleep', 'MND.coping'),
  ('BOD.exercise', 'HOB.sport'),
  ('BOD.nutrition', 'FOD.ingredient'),
  ('BOD.nutrition', 'FOD.product'),
  ('BOD.medical', 'MON.insurance'),
  // MND
  ('MND.emotion', 'REL.romance'),
  ('MND.emotion', 'REL.conflict'),
  ('MND.motivation', 'WRK.jobchange'),
  ('MND.motivation', 'EDU.online'),
  ('MND.coping', 'HOB.sport'),
  ('MND.coping', 'HOB.outdoor'),
  ('MND.coping', 'REG.practice'),
  // HOB
  ('HOB.sing', 'CUL.music'),
  ('HOB.outdoor', 'TRV.domestic'),
  ('HOB.outdoor', 'NAT.terrain'),
  ('HOB.outdoor', 'NAT.weather'),
  ('HOB.game', 'TEC.sw'),
  ('HOB.game', 'TEC.hw'),
  ('HOB.craft', 'LIV.supply'),
  ('HOB.collect', 'CUL.art'),
  ('HOB.collect', 'MON.spending'),
  ('HOB.social', 'REL.comm'),
  ('HOB.social', 'TRV.place'),
  // CUL
  ('CUL.book', 'EDU.reading'),
  ('CUL.book', 'EDU.academic'),
  ('CUL.media', 'TEC.sw'),
  ('CUL.show', 'TRV.place'),
  // WRK
  ('WRK.workplace', 'PER.colleague'),
  ('WRK.workplace', 'MON.income'),
  ('WRK.workplace', 'LAW.rights'),
  ('WRK.jobchange', 'MON.income'),
  ('WRK.cert', 'EDU.exam'),
  ('WRK.cert', 'EDU.online'),
  ('WRK.business', 'MON.income'),
  ('WRK.business', 'LAW.contract'),
  ('WRK.tool', 'TEC.sw'),
  ('WRK.tool', 'TEC.ai'),
  // MON
  ('MON.income', 'LAW.tax'),
  ('MON.payment', 'LAW.tax'),
  ('MON.loan', 'LIV.housing'),
  ('MON.loan', 'LAW.contract'),
  ('MON.insurance', 'LAW.contract'),
  ('MON.invest', 'SOC.economy'),
  // LAW
  ('LAW.contract', 'LIV.housing'),
  ('LAW.rights', 'TEC.security'),
  ('LAW.statute', 'WRK.workplace'),
  ('LAW.admin', 'LIV.moving'),
  // EDU
  ('EDU.school', 'WRK.cert'),
  ('EDU.online', 'TEC.sw'),
  ('EDU.language', 'TRV.abroad'),
  // TRV
  ('TRV.domestic', 'FOD.restaurant'),
  ('TRV.domestic', 'HOB.outdoor'),
  ('TRV.domestic', 'NAT.weather'),
  ('TRV.abroad', 'FOD.restaurant'),
  ('TRV.abroad', 'SOC.international'),
  ('TRV.place', 'NAT.terrain'),
  // NAT
  ('NAT.animal', 'LIV.supply'),
  ('NAT.ecology', 'SOC.issue'),
  // LIV
  ('LIV.housing', 'MON.loan'),
  ('LIV.housing', 'LAW.contract'),
  ('LIV.appliance', 'TEC.hw'),
  ('LIV.appliance', 'TEC.sw'),
  ('LIV.moving', 'TRV.place'),
  // TEC
  ('TEC.ai', 'SOC.issue'),
  // PER
  ('PER.colleague', 'WRK.workplace'),
  ('PER.org', 'WRK.workplace'),
  ('PER.family', 'REL.romance'),
  ('PER.friend', 'REL.comm'),
  // REL
  ('REL.conflict', 'WRK.workplace'),
  ('REL.online', 'SOC.issue'),
  // SOC
  ('SOC.international', 'TRV.abroad'),
  ('SOC.politics', 'LAW.statute'),
  // REG
  ('REG.practice', 'MND.coping'),
  // ACT
  ('ACT.eat', 'FOD.restaurant'),
  ('ACT.eat', 'FOD.ingredient'),
  ('ACT.move', 'TRV.transport'),
  ('ACT.move', 'TRV.place'),
  ('ACT.use', 'TEC.hw'),
  ('ACT.use', 'TEC.sw'),
  ('ACT.make', 'HOB.craft'),
  ('ACT.talk', 'REL.comm'),
  ('ACT.think', 'MND.motivation'),
  ('ACT.rest', 'BOD.sleep'),
  ('ACT.work', 'WRK.role'),
];

/// Expands single-direction pairs into a bidirectional adjacency map.
Map<String, List<String>> buildAdjacentMap(
  List<(String, String)> pairs,
) {
  final map = <String, List<String>>{};
  for (final (a, b) in pairs) {
    (map[a] ??= []).add(b);
    (map[b] ??= []).add(a);
  }
  return map;
}
