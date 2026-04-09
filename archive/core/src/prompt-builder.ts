import type { SubgraphResult } from './types.js';

export function formatPrompt(subgraph: SubgraphResult): string {
  const lines: string[] = [];

  if (subgraph.nodes.length > 0) {
    lines.push('[사용자 맥락 정보]');
    lines.push('');

    for (const node of subgraph.nodes) {
      const parts = [node.name];
      if (node.domain) parts.push(`(${node.domain})`);
      lines.push(`- ${parts.join(' ')}`);
    }

    if (subgraph.edges.length > 0) {
      lines.push('');
      lines.push('관계:');
      for (const edge of subgraph.edges) {
        const labelPart = edge.label ? `: ${edge.label}` : '';
        lines.push(`  ${edge.source_name} --(${edge.type}${labelPart})--> ${edge.target_name}`);
      }
    }
  }

  if (subgraph.safety_nodes.length > 0) {
    lines.push('');
    lines.push('[사용자 주의사항 — 질문과 관련될 때만 고려]');
    for (const node of subgraph.safety_nodes) {
      const rule = node.safety_rule || '관련 질문 시 고려';
      lines.push(`- ${node.name}: ${rule}`);
    }
  }

  return lines.length > 0 ? lines.join('\n') : '';
}
