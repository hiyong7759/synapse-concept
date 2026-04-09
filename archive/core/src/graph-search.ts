import type { DbAdapter, Node, EdgeWithNames, SubgraphResult, ContextResult } from './types.js';
import { formatPrompt } from './prompt-builder.js';

const PARTICLES = /(이|가|은|는|을|를|에|에서|으로|로|와|과|의|도|만|부터|까지|에게|한테|처럼|같이|보다|라도|이라도)$/;

const STOP_WORDS = new Set([
  // pronouns / determiners
  '이', '그', '저', '뭐', '뭘', '어떤', '어디', '언제', '누구', '무슨', '어떻게',
  // verb/adjective stems
  '해', '돼', '했어', '했는데', '할까', '할지', '하는', '하고', '싶', '좋', '있', '없',
  '알려', '알아', '보여', '봐', '써', '쓸', '쓰는', '됐', '되는', '된',
  '줘', '줄', '주는', '가르쳐', '찾아',
  // auxiliary / adverbs
  '안', '못', '좀', '잘', '더', '왜', '다', '또', '꼭', '너무', '많이', '조금',
  // particle remnants
  '를', '을', '수', '때', '걸', '건', '거', '게', '데',
  // generic predicates (not node names)
  '관리', '시스템', '서비스', '프로그램', '작성', '만들기', '사용', '활용',
  '경험', '추천', '정리', '설명', '비교', '차이', '방법', '설정', '구축',
  '뭐야', '뭐지', '있어', '없어', '했지', '했나', '할래', '할게',
  '살아', '사는', '갈까', '올까', '보자', '하자',
]);

const KNOWN_DOMAINS = new Set([
  '프로필', '회사', '학력', '프로젝트', '자격', '기술', '고객사',
  '역할', '조직', '직급', '업무', '위치', '경력', '병역',
  '음식', '건강', '운동', '장비', '용도', '판단', '취미',
]);

export class GraphSearch {
  constructor(private db: DbAdapter) {}

  normalizeKeywords(rawKeywords: string[]): string[] {
    const result: string[] = [];
    for (const kw of rawKeywords) {
      let stripped = kw.replace(PARTICLES, '');
      if (!stripped) stripped = kw;
      if (STOP_WORDS.has(stripped.toLowerCase())) continue;
      // skip single-char Korean
      if (stripped.length === 1 && stripped.charCodeAt(0) >= 0xAC00) continue;
      result.push(stripped);
    }
    return result;
  }

  matchStartNodes(keywords: string[], identityId: number | null): {
    results: Node[];
    domainFilters: Set<string>;
    unmatched: string[];
  } {
    if (keywords.length === 0) return { results: [], domainFilters: new Set(), unmatched: [] };

    // domain matching
    const dbDomains = new Set(
      this.db.all<{ domain: string }>(
        "SELECT DISTINCT domain FROM nodes WHERE status = 'active' AND domain != ''",
      ).map(r => r.domain),
    );
    const allDomains = new Set([...KNOWN_DOMAINS, ...dbDomains]);

    const domainFilters = new Set<string>();
    const contentKeywords: string[] = [];

    for (const kw of keywords) {
      let matchedDomain = false;
      for (const d of allDomains) {
        if (kw.toLowerCase().includes(d.toLowerCase()) || d.toLowerCase().includes(kw.toLowerCase())) {
          domainFilters.add(d);
          matchedDomain = true;
        }
      }
      if (!matchedDomain) contentKeywords.push(kw);
    }

    // alias matching + name matching
    let nameRows: Node[] = [];
    if (contentKeywords.length > 0) {
      // 1) aliases
      const aliasConds = contentKeywords.map(() => 'LOWER(a.alias) = LOWER(?)').join(' OR ');
      const aliasRows = this.db.all<Node>(
        `SELECT DISTINCT n.* FROM aliases a
         JOIN nodes n ON a.node_id = n.id
         WHERE n.status = 'active' AND (${aliasConds})
         ORDER BY n.weight DESC`,
        ...contentKeywords,
      );

      // 2) name substring
      const nameConds = contentKeywords.map(() =>
        "(LOWER(name) LIKE LOWER(?) OR LOWER(?) LIKE '%' || LOWER(name) || '%')",
      ).join(' OR ');
      const nameParams: unknown[] = [];
      for (const kw of contentKeywords) {
        nameParams.push(`%${kw}%`, kw);
      }
      const nameOnlyRows = this.db.all<Node>(
        `SELECT * FROM nodes WHERE status = 'active' AND (${nameConds}) ORDER BY weight DESC`,
        ...nameParams,
      );

      // merge, aliases first
      const seenIds = new Set<number>();
      for (const row of [...aliasRows, ...nameOnlyRows]) {
        if (!seenIds.has(row.id)) {
          seenIds.add(row.id);
          nameRows.push(row);
        }
      }
    }

    // edge type matching
    let labelRows: Node[] = [];
    if (contentKeywords.length > 0) {
      const typeConds = contentKeywords.map(() => 'LOWER(e.type) LIKE LOWER(?)').join(' OR ');
      const typeParams = contentKeywords.map(kw => `%${kw}%`);
      labelRows = this.db.all<Node>(
        `SELECT DISTINCT n.* FROM edges e
         JOIN nodes n ON (n.id = e.source_node_id OR n.id = e.target_node_id)
         WHERE n.status = 'active' AND (${typeConds})
         ORDER BY n.weight DESC`,
        ...typeParams,
      );
    }

    // dedupe
    const seen = new Set<number>();
    const results: Node[] = [];
    for (const row of nameRows) {
      if (!seen.has(row.id)) {
        seen.add(row.id);
        results.push(row);
      }
    }
    for (const row of labelRows) {
      if (!seen.has(row.id) && row.id !== identityId) {
        seen.add(row.id);
        results.push(row);
      }
    }

    // unmatched content keywords
    const matchedNames = new Set(results.map(r => r.name.toLowerCase()));
    const unmatched = contentKeywords.filter(
      kw => ![...matchedNames].some(name => name.includes(kw.toLowerCase())),
    );

    // domain fallback
    if (results.length === 0 && domainFilters.size > 0) {
      const placeholders = [...domainFilters].map(() => '?').join(',');
      const domainRows = this.db.all<Node>(
        `SELECT * FROM nodes WHERE status = 'active' AND domain IN (${placeholders})`,
        ...domainFilters,
      );
      results.push(...domainRows);
    }

    return { results, domainFilters, unmatched };
  }

  getNeighbors(nodeIds: number[], forwardOnly: boolean): (Node & { edge_type: string; source_node_id: number; target_node_id: number })[] {
    if (nodeIds.length === 0) return [];
    const placeholders = nodeIds.map(() => '?').join(',');

    if (forwardOnly) {
      return this.db.all(
        `SELECT DISTINCT n.*, e.type as edge_type, e.source_node_id, e.target_node_id
         FROM edges e
         JOIN nodes n ON e.target_node_id = n.id
         WHERE e.source_node_id IN (${placeholders})
           AND n.status = 'active' AND n.id NOT IN (${placeholders})`,
        ...nodeIds, ...nodeIds,
      );
    }

    return this.db.all(
      `SELECT DISTINCT n.*, e.type as edge_type, e.source_node_id, e.target_node_id
       FROM edges e
       JOIN nodes n ON (
           (e.target_node_id = n.id AND e.source_node_id IN (${placeholders}))
           OR
           (e.source_node_id = n.id AND e.target_node_id IN (${placeholders}))
       )
       WHERE n.status = 'active' AND n.id NOT IN (${placeholders})`,
      ...nodeIds, ...nodeIds, ...nodeIds,
    );
  }

  getSafetyNodes(): Node[] {
    return this.db.all<Node>(
      "SELECT * FROM nodes WHERE safety = 1 AND status = 'active'",
    );
  }

  getInternalEdges(nodeIds: number[]): EdgeWithNames[] {
    if (nodeIds.length === 0) return [];
    const placeholders = nodeIds.map(() => '?').join(',');
    return this.db.all<EdgeWithNames>(
      `SELECT e.*, src.name as source_name, tgt.name as target_name
       FROM edges e
       JOIN nodes src ON e.source_node_id = src.id
       JOIN nodes tgt ON e.target_node_id = tgt.id
       WHERE e.source_node_id IN (${placeholders})
         AND e.target_node_id IN (${placeholders})`,
      ...nodeIds, ...nodeIds,
    );
  }

  findIdentityNode(): number | null {
    const row = this.db.get<{ node_id: number }>(
      `SELECT node_id, COUNT(*) as cnt FROM (
           SELECT source_node_id as node_id FROM edges
           UNION ALL
           SELECT target_node_id as node_id FROM edges
       ) GROUP BY node_id ORDER BY cnt DESC LIMIT 1`,
    );
    return row?.node_id ?? null;
  }

  private bfsFrom(startId: number, identityId: number | null): Set<number> {
    const visited = new Set([startId]);
    let queue = [startId];
    while (queue.length > 0) {
      const neighbors = this.getNeighbors(queue, true);
      const nextQueue: number[] = [];
      for (const n of neighbors) {
        if (!visited.has(n.id)) {
          if (n.safety) continue;
          visited.add(n.id);
          if (n.id === identityId) continue;
          nextQueue.push(n.id);
        }
      }
      queue = nextQueue;
    }
    return visited;
  }

  private areConnected(idA: number, idB: number): boolean {
    const row = this.db.get(
      `SELECT 1 FROM edges
       WHERE (source_node_id = ? AND target_node_id = ?)
          OR (source_node_id = ? AND target_node_id = ?)
       LIMIT 1`,
      idA, idB, idB, idA,
    );
    return row !== undefined;
  }

  buildSubgraph(keywords: string[]): SubgraphResult {
    const identityId = this.findIdentityNode();
    const { results: startNodes, domainFilters, unmatched } =
      this.matchStartNodes(keywords, identityId);

    const safeStartNodes = startNodes.filter(n => !n.safety);
    const startIds = [...new Set(safeStartNodes.map(n => n.id))];

    // Per-node BFS, then intersect connected groups / union unconnected
    let allReached: Set<number>;

    if (startIds.length <= 1) {
      allReached = startIds.length === 1 ? this.bfsFrom(startIds[0], identityId) : new Set();
    } else {
      const perNodeSets = new Map(startIds.map(sid => [sid, this.bfsFrom(sid, identityId)]));

      // group connected start nodes
      const connectedGroups: Set<number>[] = [];
      const ungrouped = new Set(startIds);
      for (const sid of startIds) {
        if (!ungrouped.has(sid)) continue;
        const group = new Set([sid]);
        ungrouped.delete(sid);
        for (const other of [...ungrouped]) {
          if (this.areConnected(sid, other)) {
            group.add(other);
            ungrouped.delete(other);
          }
        }
        connectedGroups.push(group);
      }

      // intersect within group, union across groups
      allReached = new Set();
      for (const group of connectedGroups) {
        const groupIds = [...group];
        let intersected = perNodeSets.get(groupIds[0])!;
        for (let i = 1; i < groupIds.length; i++) {
          const other = perNodeSets.get(groupIds[i])!;
          const next = new Set<number>();
          for (const id of intersected) {
            if (other.has(id)) next.add(id);
          }
          intersected = next;
        }
        for (const id of intersected) allReached.add(id);
      }
    }

    // fetch node details
    let allNodes: Node[] = [];
    if (allReached.size > 0) {
      const reachedIds = [...allReached];
      const placeholders = reachedIds.map(() => '?').join(',');
      allNodes = this.db.all<Node>(
        `SELECT * FROM nodes WHERE id IN (${placeholders}) AND status = 'active'`,
        ...reachedIds,
      );
    }
    let allIds = allNodes.map(n => n.id);

    // domain filter: keep only matching domain results
    if (domainFilters.size > 0 && allNodes.length > 0) {
      const filtered = allNodes.filter(n => domainFilters.has(n.domain));
      if (filtered.length > 0) {
        allNodes = filtered;
        allIds = allNodes.map(n => n.id);
      }
    }

    const safetyNodes = this.getSafetyNodes();
    const edges = this.getInternalEdges(allIds);

    // missing info
    const missing: string[] = [];
    for (const kw of unmatched) {
      missing.push(`"${kw}" 노드가 없습니다. 추가하시겠어요?`);
    }
    if (allNodes.length === 0 && domainFilters.size > 0) {
      for (const d of domainFilters) {
        const count = this.db.get<{ cnt: number }>(
          "SELECT COUNT(*) as cnt FROM nodes WHERE status = 'active' AND domain = ?", d,
        );
        if ((count?.cnt ?? 0) === 0) {
          missing.push(`"${d}" 관련 노드가 없습니다. 추가하시겠어요?`);
        }
      }
    }

    return {
      start_nodes: safeStartNodes.map(n => n.name),
      nodes: allNodes,
      edges,
      safety_nodes: safetyNodes,
      missing,
    };
  }

  incrementWeights(nodeIds: number[]): void {
    if (nodeIds.length === 0) return;
    const placeholders = nodeIds.map(() => '?').join(',');
    this.db.run(
      `UPDATE nodes SET weight = weight + 1, updated_at = datetime('now') WHERE id IN (${placeholders})`,
      ...nodeIds,
    );
  }

  updateEdgesLastUsed(nodeIds: number[]): void {
    if (nodeIds.length === 0) return;
    const placeholders = nodeIds.map(() => '?').join(',');
    this.db.run(
      `UPDATE edges SET last_used = datetime('now')
       WHERE source_node_id IN (${placeholders})
         AND target_node_id IN (${placeholders})`,
      ...nodeIds, ...nodeIds,
    );
  }

  getContext(query: string): ContextResult {
    const rawKeywords = query.split(/\s+/).filter(Boolean);
    const keywords = this.normalizeKeywords(rawKeywords);

    const subgraph = this.buildSubgraph(keywords);
    const prompt = formatPrompt(subgraph);

    const nodeIds = subgraph.nodes.map(n => n.id);
    if (nodeIds.length > 0) {
      this.incrementWeights(nodeIds);
      this.updateEdgesLastUsed(nodeIds);
    }

    const result: ContextResult = {
      status: 'ok',
      prompt,
      nodes_used: subgraph.nodes.map(n => n.name),
      safety_nodes: subgraph.safety_nodes.map(n => n.name),
      node_count: subgraph.nodes.length,
      edge_count: subgraph.edges.length,
    };
    if (subgraph.missing.length > 0) {
      result.missing = subgraph.missing;
    }
    return result;
  }
}
