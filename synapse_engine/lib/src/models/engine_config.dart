import 'dart:async';

import 'triple.dart';

/// Category definition for knowledge graph nodes.
class Category {
  final String code;
  final String name;
  final List<String> subcategories;

  const Category(this.code, this.name, this.subcategories);
}

/// Category map — injected by consumer app.
class CategoryMap {
  final Map<String, Category> _categories;

  const CategoryMap(this._categories);

  /// Default Synapse 17-category system.
  factory CategoryMap.synapse() => const CategoryMap(_defaultCategories);

  Category? operator [](String code) => _categories[code];
  Iterable<String> get codes => _categories.keys;
  Iterable<Category> get values => _categories.values;
}

/// Adjacent subcategory map for BFS supplementation.
class AdjacencyMap {
  final Map<String, List<String>> _adjacency;

  const AdjacencyMap(this._adjacency);

  /// Default Synapse adjacency map.
  factory AdjacencyMap.synapse() => const AdjacencyMap(_defaultAdjacency);

  List<String> getAdjacent(String subcategory) =>
      _adjacency[subcategory] ?? [];

  bool get isEmpty => _adjacency.isEmpty;
  Iterable<String> get keys => _adjacency.keys;

  /// Convert to plain map (for passing to retrieve).
  Map<String, List<String>> toMap() => Map.unmodifiable(_adjacency);
}

/// LoRA adapter specification.
class AdapterSpec {
  final String name;
  final String path;
  final String? systemPrompt;
  final int maxTokens;
  final double temperature;

  const AdapterSpec({
    required this.name,
    required this.path,
    this.systemPrompt,
    this.maxTokens = 512,
    this.temperature = 0.0,
  });
}

/// Model source — bundled, download, or local file.
abstract class ModelSource {
  const ModelSource();

  factory ModelSource.file(String path) = FileModelSource;
  factory ModelSource.bundled(String assetPath) = BundledModelSource;
}

class FileModelSource extends ModelSource {
  final String path;
  const FileModelSource(this.path);
}

class BundledModelSource extends ModelSource {
  final String assetPath;
  const BundledModelSource(this.assetPath);
}

/// Engine configuration.
class EngineConfig {
  final String dataDir;
  final String modelPath;
  final String adapterDir;
  final List<AdapterSpec> customAdapters;
  final CategoryMap categories;
  final AdjacencyMap adjacency;
  final String locale;
  final Map<String, String>? systemPromptOverrides;
  final Map<String, int>? maxTokensOverrides;

  // Pipeline hooks
  final Future<Map<String, dynamic>> Function(
      Map<String, dynamic> raw)? onAfterExtract;
  final Future<String> Function(String text)? onBeforePronoun;
  final Future<List<Triple>> Function(
      List<Triple> triples, String query)? onAfterRetrieve;
  final String Function(
      String defaultSystemPrompt, List<Triple> context)? onBuildChatPrompt;

  const EngineConfig({
    required this.dataDir,
    required this.modelPath,
    required this.adapterDir,
    this.customAdapters = const [],
    CategoryMap? categories,
    AdjacencyMap? adjacency,
    this.locale = 'ko',
    this.systemPromptOverrides,
    this.maxTokensOverrides,
    this.onAfterExtract,
    this.onBeforePronoun,
    this.onAfterRetrieve,
    this.onBuildChatPrompt,
  })  : categories = categories ?? const CategoryMap(_defaultCategories),
        adjacency = adjacency ?? const AdjacencyMap(_defaultAdjacency);
}

// ── Default Synapse categories (17) ──────────────────────

const _defaultCategories = <String, Category>{
  'PER': Category('PER', '인물', ['self', 'family', 'friend', 'colleague', 'public']),
  'BOD': Category('BOD', '건강', ['disease', 'symptom', 'treatment', 'exercise', 'checkup']),
  'MND': Category('MND', '심리', ['emotion', 'stress', 'mental', 'therapy']),
  'FOD': Category('FOD', '음식', ['meal', 'recipe', 'restaurant', 'diet', 'allergy']),
  'LIV': Category('LIV', '주거', ['home', 'appliance', 'interior', 'move', 'repair']),
  'MON': Category('MON', '금융', ['income', 'spending', 'saving', 'invest', 'tax', 'insurance', 'debt']),
  'WRK': Category('WRK', '직업', ['company', 'role', 'project', 'colleague', 'career']),
  'TEC': Category('TEC', '기술', ['device', 'software', 'programming', 'ai', 'network']),
  'EDU': Category('EDU', '교육', ['school', 'cert', 'study', 'reading', 'language']),
  'LAW': Category('LAW', '법', ['contract', 'dispute', 'regulation', 'rights']),
  'TRV': Category('TRV', '여행', ['domestic', 'overseas', 'transport', 'lodging', 'plan']),
  'NAT': Category('NAT', '자연', ['weather', 'season', 'plant', 'animal', 'environment']),
  'CUL': Category('CUL', '문화', ['film', 'music', 'book', 'art', 'game', 'show']),
  'HOB': Category('HOB', '취미', ['sport', 'craft', 'collect', 'outdoor', 'cooking']),
  'SOC': Category('SOC', '사회', ['news', 'politics', 'community', 'volunteer']),
  'REL': Category('REL', '관계', ['family', 'friendship', 'romantic', 'professional']),
  'REG': Category('REG', '종교', ['faith', 'practice', 'community', 'philosophy']),
};

// ── Default adjacency map ────────────────────────────────

const _defaultAdjacency = <String, List<String>>{
  'BOD.disease': ['MND.mental', 'BOD.treatment', 'BOD.symptom'],
  'BOD.exercise': ['HOB.sport', 'BOD.symptom'],
  'BOD.symptom': ['BOD.disease', 'BOD.treatment', 'MND.stress'],
  'BOD.treatment': ['BOD.disease', 'MON.spending', 'BOD.symptom'],
  'BOD.checkup': ['BOD.disease', 'BOD.symptom'],
  'MND.emotion': ['MND.stress', 'REL.friendship', 'REL.romantic'],
  'MND.stress': ['MND.emotion', 'WRK.company', 'BOD.symptom'],
  'MND.mental': ['BOD.disease', 'MND.stress', 'MND.therapy'],
  'MND.therapy': ['MND.mental', 'MND.stress', 'MON.spending'],
  'FOD.meal': ['FOD.restaurant', 'FOD.diet', 'HOB.cooking'],
  'FOD.restaurant': ['FOD.meal', 'MON.spending', 'TRV.domestic'],
  'FOD.diet': ['FOD.meal', 'BOD.exercise', 'BOD.symptom'],
  'FOD.allergy': ['BOD.symptom', 'FOD.meal', 'BOD.treatment'],
  'MON.income': ['WRK.company', 'MON.tax', 'MON.saving'],
  'MON.spending': ['MON.income', 'FOD.restaurant', 'TRV.domestic'],
  'MON.saving': ['MON.income', 'MON.invest'],
  'MON.invest': ['MON.saving', 'MON.income', 'TEC.ai'],
  'MON.tax': ['MON.income', 'LAW.regulation'],
  'MON.insurance': ['MON.spending', 'BOD.disease', 'LAW.contract'],
  'MON.debt': ['MON.income', 'MON.spending', 'MND.stress'],
  'WRK.company': ['WRK.role', 'WRK.colleague', 'MON.income'],
  'WRK.role': ['WRK.company', 'WRK.project', 'WRK.career'],
  'WRK.project': ['WRK.role', 'TEC.programming', 'WRK.colleague'],
  'WRK.colleague': ['WRK.company', 'REL.professional', 'MND.stress'],
  'WRK.career': ['WRK.role', 'EDU.cert', 'WRK.company'],
  'TEC.device': ['TEC.software', 'MON.spending', 'LIV.appliance'],
  'TEC.software': ['TEC.device', 'TEC.programming'],
  'TEC.programming': ['TEC.software', 'WRK.project', 'EDU.study'],
  'TEC.ai': ['TEC.programming', 'EDU.study', 'MON.invest'],
  'EDU.school': ['EDU.study', 'EDU.cert'],
  'EDU.cert': ['EDU.study', 'WRK.career'],
  'EDU.study': ['EDU.school', 'EDU.reading', 'TEC.programming'],
  'EDU.reading': ['EDU.study', 'CUL.book'],
  'EDU.language': ['EDU.study', 'TRV.overseas'],
  'TRV.domestic': ['TRV.transport', 'TRV.lodging', 'FOD.restaurant'],
  'TRV.overseas': ['TRV.transport', 'TRV.lodging', 'EDU.language'],
  'TRV.transport': ['TRV.domestic', 'TRV.overseas', 'MON.spending'],
  'TRV.lodging': ['TRV.domestic', 'TRV.overseas', 'MON.spending'],
  'CUL.film': ['CUL.show', 'HOB.collect'],
  'CUL.music': ['HOB.collect', 'MND.emotion'],
  'CUL.book': ['EDU.reading', 'HOB.collect'],
  'CUL.game': ['TEC.software', 'HOB.collect'],
  'HOB.sport': ['BOD.exercise', 'HOB.outdoor'],
  'HOB.craft': ['HOB.collect', 'CUL.art'],
  'HOB.outdoor': ['HOB.sport', 'NAT.environment', 'TRV.domestic'],
  'HOB.cooking': ['FOD.meal', 'FOD.recipe'],
  'REL.family': ['REL.romantic', 'MND.emotion'],
  'REL.friendship': ['MND.emotion', 'REL.professional'],
  'REL.romantic': ['REL.family', 'MND.emotion'],
  'REL.professional': ['WRK.colleague', 'REL.friendship'],
  'LIV.home': ['LIV.interior', 'LIV.repair', 'MON.spending'],
  'LIV.appliance': ['TEC.device', 'LIV.home', 'MON.spending'],
  'LIV.move': ['LIV.home', 'MON.spending', 'MND.stress'],
  'LIV.repair': ['LIV.home', 'MON.spending'],
  'LAW.contract': ['LAW.dispute', 'MON.insurance'],
  'LAW.dispute': ['LAW.contract', 'MND.stress'],
  'LAW.regulation': ['MON.tax', 'LAW.rights'],
};
