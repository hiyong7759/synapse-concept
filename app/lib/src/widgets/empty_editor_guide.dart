import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// Shown in the editor area when no post is selected. Bullet examples are
/// pulled from `docs/DESIGN_INPUT_MODES_AND_RETRIEVAL.md` §4-가지 요소
/// 판단표 — same vocabulary so the user sees in the empty state exactly
/// what the engine expects later.
class EmptyEditorGuide extends StatelessWidget {
  const EmptyEditorGuide({super.key});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560),
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(
            horizontal: SynapseTokens.spaceL,
            vertical: SynapseTokens.spaceXl,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: const [
              _GuideHeader(),
              SizedBox(height: SynapseTokens.spaceL),
              _GuideExample(
                icon: '📝',
                title: '자유롭게 적기',
                subtitle: '즉흥 메모, 감정 기록 — 그냥 평문으로',
                examples: [
                  '오늘 허리가 좀 아팠다',
                  '팀 회의 결정 — 모바일 우선',
                ],
              ),
              SizedBox(height: SynapseTokens.spaceL),
              _GuideExample(
                icon: '📂',
                title: '제목으로 묶기',
                subtitle: 'heading 으로 분류 경로 등록',
                examples: [
                  '## 제1장 총칙',
                  '### 제1조 (목적)',
                  '이 규칙은 ... 목적으로 한다.',
                ],
              ),
              SizedBox(height: SynapseTokens.spaceL),
              _GuideExample(
                icon: '🔖',
                title: '용어·속성 정의',
                subtitle: '`- key:: value` — 콜론 두 개',
                examples: [
                  '- 보직:: 직원 자질에 따라 부여',
                  '- 개정일:: 2025-04-30',
                ],
              ),
              SizedBox(height: SynapseTokens.spaceL),
              _GuideExample(
                icon: '📋',
                title: '항목 나열',
                subtitle: '같은 묶음 안 여러 항목',
                examples: [
                  '- 이력서 1통',
                  '- 자기소개서 1통',
                ],
              ),
              SizedBox(height: SynapseTokens.spaceL),
              _GuideExample(
                icon: '➡️',
                title: '한 줄 경로',
                subtitle: '점(.)으로 분류 경로 한 번에',
                examples: [
                  '# 취업규칙.제1장 총칙.제1조 (목적)',
                  '이 규칙은 ... 목적으로 한다.',
                ],
              ),
              SizedBox(height: SynapseTokens.spaceXl),
              _GuideFooter(),
            ],
          ),
        ),
      ),
    );
  }
}

class _GuideHeader extends StatelessWidget {
  const _GuideHeader();

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '노트를 시작하세요',
          style: SynapseTokens.display.copyWith(fontSize: 24),
        ),
        const SizedBox(height: SynapseTokens.spaceXs),
        const Text(
          '왼쪽 [+ 새 노트] 또는 기존 노트 선택. 어떻게 적든 같은 그릇입니다.',
          style: SynapseTokens.caption,
        ),
      ],
    );
  }
}

class _GuideExample extends StatelessWidget {
  const _GuideExample({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.examples,
  });

  final String icon;
  final String title;
  final String subtitle;
  final List<String> examples;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 28,
          child: Text(icon, style: const TextStyle(fontSize: 18)),
        ),
        const SizedBox(width: SynapseTokens.spaceS),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: SynapseTokens.title),
              const SizedBox(height: 2),
              Text(subtitle, style: SynapseTokens.caption),
              const SizedBox(height: SynapseTokens.spaceS),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: SynapseTokens.spaceM,
                  vertical: SynapseTokens.spaceS,
                ),
                decoration: BoxDecoration(
                  color: SynapseTokens.surface,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(
                    color: SynapseTokens.background,
                    width: 1,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (final line in examples)
                      Text(
                        line,
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 13,
                          height: 1.6,
                          color: SynapseTokens.onSurface,
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _GuideFooter extends StatelessWidget {
  const _GuideFooter();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(SynapseTokens.spaceM),
      decoration: BoxDecoration(
        color: SynapseTokens.surface,
        borderRadius: BorderRadius.circular(6),
      ),
      child: const Row(
        children: [
          Text('💾', style: TextStyle(fontSize: 16)),
          SizedBox(width: SynapseTokens.spaceS),
          Expanded(
            child: Text(
              '입력 후 1.5초 멈추면 자동 저장. 페이지 떠나도 본문은 살아 있습니다.',
              style: SynapseTokens.caption,
            ),
          ),
        ],
      ),
    );
  }
}
