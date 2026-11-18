import type { GraphData } from '../types';

/** Three clickable example questions derived from the loaded graph. */
export function exampleQuestions(graph: GraphData): string[] {
  const name = new Map(graph.entities.map((e) => [e.id, e.canonical_name]));
  const type = new Map(graph.entities.map((e) => [e.id, e.type]));
  const out = new Map<string, string[]>();
  const adj = new Map<string, Set<string>>();
  for (const r of graph.relationships) {
    if (!out.has(r.source_id)) out.set(r.source_id, []);
    out.get(r.source_id)!.push(r.id);
    for (const [a, b] of [[r.source_id, r.target_id], [r.target_id, r.source_id]]) {
      if (!adj.has(a)) adj.set(a, new Set());
      adj.get(a)!.add(b);
    }
  }
  const byId = new Map(graph.relationships.map((r) => [r.id, r]));
  const questions: string[] = [];

  // 1. chained: X -invested_in-> Y -uses_infrastructure-> Z
  const mentions = new Map(graph.entities.map((e) => [e.id, e.mention_count]));
  const investments = graph.relationships
    .filter((r) => r.relation === 'invested_in')
    .sort((a, b) => (mentions.get(b.source_id) ?? 0) - (mentions.get(a.source_id) ?? 0));
  outer: for (const r1 of investments) {
    for (const rid of out.get(r1.target_id) ?? []) {
      if (byId.get(rid)?.relation === 'uses_infrastructure') {
        questions.push(`Which cloud infrastructure is associated with the company ${name.get(r1.source_id)} invested in?`);
        break outer;
      }
    }
  }

  // 2. relation lookup
  const founded = graph.relationships.find((r) => r.relation === 'founded');
  const worksAt = graph.relationships.find((r) => r.relation === 'works_at');
  const invested = graph.relationships.find((r) => r.relation === 'invested_in');
  if (founded) questions.push(`Who founded ${name.get(founded.target_id)}?`);
  else if (worksAt) questions.push(`Where does ${name.get(worksAt.source_id)} work?`);
  else if (invested) questions.push(`Who invested in ${name.get(invested.target_id)}?`);

  // 3. connection: a person and an organization exactly 2-3 hops apart
  const people = graph.entities.filter((e) => e.type === 'PERSON' && adj.has(e.id));
  search: for (const p of people) {
    const dist = new Map<string, number>([[p.id, 0]]);
    const queue = [p.id];
    while (queue.length) {
      const cur = queue.shift()!;
      for (const n of adj.get(cur) ?? []) {
        if (dist.has(n)) continue;
        dist.set(n, dist.get(cur)! + 1);
        queue.push(n);
      }
    }
    for (const [id, d] of dist) {
      if (d >= 2 && d <= 3 && type.get(id) === 'ORG') {
        questions.push(`How are ${p.canonical_name} and ${name.get(id)} connected?`);
        break search;
      }
    }
  }

  if (questions.length < 3 && graph.entities[0]) {
    questions.push(`Tell me about ${graph.entities[0].canonical_name}`);
  }
  return questions.slice(0, 3);
}
