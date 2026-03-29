import type {
  DbAdapter, Node, EdgeWithNames, AddNodeInput, AddEdgeInput,
  BatchInput, BatchResult, ListNodesFilter, DomainSummary,
  ShowNodeResult, DeactivateResult,
} from './types.js';

export class GraphStore {
  constructor(private db: DbAdapter) {}

  findNode(name: string): Node | undefined {
    // exact match first
    const exact = this.db.get<Node>(
      'SELECT * FROM nodes WHERE LOWER(name) = LOWER(?)', name,
    );
    if (exact) return exact;
    // substring fallback
    return this.db.get<Node>(
      'SELECT * FROM nodes WHERE LOWER(name) LIKE LOWER(?) ORDER BY weight DESC LIMIT 1',
      `%${name}%`,
    );
  }

  addNode(input: AddNodeInput): { id: number; is_new: boolean } {
    const existing = this.db.get<Node>(
      'SELECT * FROM nodes WHERE LOWER(name) = LOWER(?)', input.name,
    );
    if (existing) return { id: existing.id, is_new: false };

    const { lastInsertRowid } = this.db.run(
      'INSERT INTO nodes (name, domain, source, safety, safety_rule) VALUES (?, ?, ?, ?, ?)',
      input.name,
      input.domain ?? '',
      input.source ?? 'user',
      input.safety ? 1 : 0,
      input.safety_rule ?? null,
    );
    return { id: Number(lastInsertRowid), is_new: true };
  }

  addEdge(sourceId: number, targetId: number, type = 'link', label: string | null = null): void {
    this.db.run(
      'INSERT OR IGNORE INTO edges (source_node_id, target_node_id, type, label) VALUES (?, ?, ?, ?)',
      sourceId, targetId, type, label,
    );
  }

  addBatch(data: BatchInput): BatchResult {
    const addedNodes: BatchResult['nodes'] = [];
    const addedEdges: BatchResult['edges'] = [];
    const nameToId = new Map<string, number>();

    // nodes
    for (const nodeData of data.nodes ?? []) {
      const { id, is_new } = this.addNode(nodeData);
      nameToId.set(nodeData.name, id);
      addedNodes.push({ id, name: nodeData.name, is_new });
    }

    // edges
    for (const edgeData of data.edges ?? []) {
      let sourceId = nameToId.get(edgeData.source);
      if (sourceId === undefined) {
        const node = this.findNode(edgeData.source);
        sourceId = node?.id;
      }
      let targetId = nameToId.get(edgeData.target);
      if (targetId === undefined) {
        const node = this.findNode(edgeData.target);
        targetId = node?.id;
      }
      if (sourceId !== undefined && targetId !== undefined) {
        const type = edgeData.type ?? 'link';
        const label = edgeData.label ?? null;
        this.addEdge(sourceId, targetId, type, label);
        addedEdges.push({ source: edgeData.source, target: edgeData.target, type, label });
      }
    }

    return {
      status: 'ok',
      nodes_added: addedNodes.length,
      edges_added: addedEdges.length,
      nodes: addedNodes,
      edges: addedEdges,
    };
  }

  updateNode(name: string, updates: Record<string, unknown>): { status: string; node?: Node; message?: string } {
    const node = this.findNode(name);
    if (!node) return { status: 'error', message: `노드 '${name}'을 찾을 수 없습니다.` };

    const allowed = new Set(['name', 'domain', 'status', 'safety', 'safety_rule']);
    const sets: string[] = [];
    const params: unknown[] = [];

    for (const [key, value] of Object.entries(updates)) {
      if (allowed.has(key)) {
        sets.push(`${key} = ?`);
        params.push(value);
      }
    }
    if (sets.length === 0) return { status: 'error', message: '수정할 필드가 없습니다.' };

    sets.push("updated_at = datetime('now')");
    params.push(node.id);

    this.db.run(`UPDATE nodes SET ${sets.join(', ')} WHERE id = ?`, ...params);

    const updated = this.db.get<Node>('SELECT * FROM nodes WHERE id = ?', node.id);
    return { status: 'ok', node: updated };
  }

  deactivateNode(name: string): DeactivateResult | { status: string; message: string } {
    const node = this.findNode(name);
    if (!node) return { status: 'error', message: `노드 '${name}'을 찾을 수 없습니다.` };

    this.db.run(
      "UPDATE nodes SET status = 'inactive', updated_at = datetime('now') WHERE id = ?",
      node.id,
    );

    // find orphans
    const connected = this.db.all<{ id: number; name: string }>(
      `SELECT DISTINCT n.id, n.name FROM edges e
       JOIN nodes n ON (
           (e.target_node_id = n.id AND e.source_node_id = ?)
           OR (e.source_node_id = n.id AND e.target_node_id = ?)
       )
       WHERE n.status = 'active'`,
      node.id, node.id,
    );

    const orphans: string[] = [];
    for (const cn of connected) {
      const other = this.db.get<{ cnt: number }>(
        `SELECT COUNT(*) as cnt FROM edges e
         JOIN nodes n1 ON e.source_node_id = n1.id
         JOIN nodes n2 ON e.target_node_id = n2.id
         WHERE (e.source_node_id = ? OR e.target_node_id = ?)
           AND e.source_node_id != ? AND e.target_node_id != ?
           AND n1.status = 'active' AND n2.status = 'active'`,
        cn.id, cn.id, node.id, node.id,
      );
      if ((other?.cnt ?? 0) === 0) orphans.push(cn.name);
    }

    const result: DeactivateResult = { status: 'ok', node: name, new_status: 'inactive' };
    if (orphans.length > 0) {
      result.orphans = orphans;
      result.message = `다음 노드가 고아가 됩니다: ${orphans.join(', ')}`;
    }
    return result;
  }

  restoreNode(name: string): { status: string; node?: string; new_status?: string; message?: string } {
    const node = this.db.get<Node>(
      "SELECT * FROM nodes WHERE LOWER(name) = LOWER(?) AND status = 'inactive'",
      name,
    );
    if (!node) return { status: 'error', message: `복원할 노드 '${name}'을 찾을 수 없습니다.` };

    this.db.run(
      "UPDATE nodes SET status = 'active', updated_at = datetime('now') WHERE id = ?",
      node.id,
    );
    return { status: 'ok', node: name, new_status: 'active' };
  }

  deleteEdge(sourceName: string, targetName: string): { status: string; deleted?: string; message?: string } {
    const edge = this.findEdge(sourceName, targetName);
    if (!edge) return { status: 'error', message: `'${sourceName}' ── '${targetName}' 엣지를 찾을 수 없습니다.` };

    this.db.run('DELETE FROM edges WHERE id = ?', edge.id);
    return { status: 'ok', deleted: `${edge.source_name} --(${edge.type})--> ${edge.target_name}` };
  }

  updateEdge(sourceName: string, targetName: string, updates: Record<string, unknown>): { status: string; edge?: EdgeWithNames; message?: string } {
    const edge = this.findEdge(sourceName, targetName);
    if (!edge) return { status: 'error', message: `'${sourceName}' ── '${targetName}' 엣지를 찾을 수 없습니다.` };

    const allowed = new Set(['type', 'label']);
    const sets: string[] = [];
    const params: unknown[] = [];

    for (const [key, value] of Object.entries(updates)) {
      if (allowed.has(key)) {
        sets.push(`${key} = ?`);
        params.push(value);
      }
    }
    if (sets.length === 0) return { status: 'error', message: '수정할 필드가 없습니다. (type, label)' };

    params.push(edge.id);
    this.db.run(`UPDATE edges SET ${sets.join(', ')} WHERE id = ?`, ...params);

    const updated = this.db.get<EdgeWithNames>(
      `SELECT e.*, src.name as source_name, tgt.name as target_name
       FROM edges e
       JOIN nodes src ON e.source_node_id = src.id
       JOIN nodes tgt ON e.target_node_id = tgt.id
       WHERE e.id = ?`,
      edge.id,
    );
    return { status: 'ok', edge: updated };
  }

  listNodes(filters?: ListNodesFilter): { status: string; count: number; nodes: Node[] } {
    const conditions: string[] = [];
    const params: unknown[] = [];

    const status = filters?.status ?? 'active';
    if (status) {
      conditions.push('status = ?');
      params.push(status);
    }
    if (filters?.domain) {
      conditions.push('LOWER(domain) = LOWER(?)');
      params.push(filters.domain);
    }
    if (filters?.search) {
      conditions.push('LOWER(name) LIKE LOWER(?)');
      params.push(`%${filters.search}%`);
    }

    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    const limit = filters?.limit ?? 100;
    params.push(limit);

    const nodes = this.db.all<Node>(
      `SELECT * FROM nodes ${where} ORDER BY weight DESC, updated_at DESC LIMIT ?`,
      ...params,
    );
    return { status: 'ok', count: nodes.length, nodes };
  }

  listEdges(nodeName?: string, limit = 100): { status: string; count: number; edges: EdgeWithNames[] } {
    let edges: EdgeWithNames[];
    if (nodeName) {
      edges = this.db.all<EdgeWithNames>(
        `SELECT e.*, src.name as source_name, tgt.name as target_name
         FROM edges e
         JOIN nodes src ON e.source_node_id = src.id
         JOIN nodes tgt ON e.target_node_id = tgt.id
         WHERE LOWER(src.name) = LOWER(?) OR LOWER(tgt.name) = LOWER(?)
         ORDER BY e.created_at DESC LIMIT ?`,
        nodeName, nodeName, limit,
      );
    } else {
      edges = this.db.all<EdgeWithNames>(
        `SELECT e.*, src.name as source_name, tgt.name as target_name
         FROM edges e
         JOIN nodes src ON e.source_node_id = src.id
         JOIN nodes tgt ON e.target_node_id = tgt.id
         ORDER BY e.created_at DESC LIMIT ?`,
        limit,
      );
    }
    return { status: 'ok', count: edges.length, edges };
  }

  listDomains(): { status: string; domains: DomainSummary[] } {
    const rows = this.db.all<DomainSummary>(
      `SELECT domain, COUNT(*) as count
       FROM nodes WHERE status = 'active'
       GROUP BY domain ORDER BY count DESC`,
    );
    return { status: 'ok', domains: rows };
  }

  showNode(name: string): ShowNodeResult | { status: string; message: string } {
    const node = this.findNode(name);
    if (!node) return { status: 'error', message: `노드 '${name}'을 찾을 수 없습니다.` };

    const edges = this.db.all<EdgeWithNames>(
      `SELECT e.*, src.name as source_name, tgt.name as target_name
       FROM edges e
       JOIN nodes src ON e.source_node_id = src.id
       JOIN nodes tgt ON e.target_node_id = tgt.id
       WHERE e.source_node_id = ? OR e.target_node_id = ?`,
      node.id, node.id,
    );
    return { status: 'ok', node, edges };
  }

  private findEdge(sourceName: string, targetName: string): EdgeWithNames | undefined {
    return this.db.get<EdgeWithNames>(
      `SELECT e.*, src.name as source_name, tgt.name as target_name
       FROM edges e
       JOIN nodes src ON e.source_node_id = src.id
       JOIN nodes tgt ON e.target_node_id = tgt.id
       WHERE (LOWER(src.name) = LOWER(?) AND LOWER(tgt.name) = LOWER(?))
          OR (LOWER(src.name) = LOWER(?) AND LOWER(tgt.name) = LOWER(?))`,
      sourceName, targetName, targetName, sourceName,
    );
  }
}
