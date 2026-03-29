import { createSynapse } from './index.js';
import { join } from 'path';
import { homedir } from 'os';

const dbPath = join(homedir(), '.synapse', 'synapse.db');
const synapse = createSynapse(dbPath);

console.log('=== Synapse Core Verification ===\n');

// 1. listDomains
const domains = synapse.store.listDomains();
console.log(`1. listDomains: ${domains.domains.length}개 도메인`);
for (const d of domains.domains.slice(0, 5)) {
  console.log(`   ${d.domain}: ${d.count}개`);
}
console.log('');

// 2. getContext tests
const tests = [
  { query: '맥미니 개발환경', expect: '4+노드' },
  { query: '학력', expect: '학력만' },
  { query: '건강 관리', expect: '0노드+missing' },
  { query: '회사에서 뭐 했어', expect: '회사 4개' },
  { query: 'React Native', expect: '1노드' },
  { query: '이력서', expect: '3노드' },
  { query: 'Poomacy 프로젝트', expect: '프로젝트+missing' },
];

for (const t of tests) {
  const result = synapse.search.getContext(t.query);
  const missing = result.missing ? `, missing: ${result.missing.length}` : '';
  console.log(`2. "${t.query}" → ${result.node_count}노드, ${result.edge_count}엣지${missing} (expect: ${t.expect})`);
}
console.log('');

// 3. addBatch + deactivate + restore
console.log('3. CRUD cycle:');
const batch = synapse.store.addBatch({
  nodes: [{ name: 'VerifyTS', domain: '기술' }],
  edges: [{ source: 'VerifyTS', target: 'React Native', type: 'link', label: 'test' }],
});
console.log(`   add: ${batch.nodes_added} nodes, ${batch.edges_added} edges`);

const deact = synapse.store.deactivateNode('VerifyTS');
console.log(`   deactivate: ${JSON.stringify(deact)}`);

const restore = synapse.store.restoreNode('VerifyTS');
console.log(`   restore: ${JSON.stringify(restore)}`);

// cleanup
synapse.store.deactivateNode('VerifyTS');

synapse.close();
console.log('\n=== Done ===');
