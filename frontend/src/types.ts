// Mirrors backend/app/models.py

export type EntityType = 'PERSON' | 'ORG' | 'TECHNOLOGY' | 'PRODUCT' | 'LOCATION' | 'OTHER';

export const ENTITY_TYPES: EntityType[] = ['PERSON', 'ORG', 'TECHNOLOGY', 'PRODUCT', 'LOCATION', 'OTHER'];

export const RELATION_TYPES = [
  'founded', 'works_at', 'invested_in', 'acquired', 'partnered_with',
  'uses', 'uses_infrastructure', 'developed', 'located_in',
  'competes_with', 'part_of', 'collaborates_with', 'related_to',
] as const;

export interface Entity {
  id: string;
  canonical_name: string;
  type: EntityType;
  aliases: string[];
  mention_count: number;
}

export interface Evidence {
  document_id: string;
  document_name: string;
  chunk_index: number;
  sentence: string;
}

export interface Relationship {
  id: string;
  source_id: string;
  target_id: string;
  relation: string;
  confidence: number;
  evidence: Evidence[];
}

export interface GraphData {
  graph_id: string;
  entities: Entity[];
  relationships: Relationship[];
}

export interface GraphStats {
  node_count: number;
  edge_count: number;
  connected_components: number;
  removed_self_loops: number;
  removed_dangling_edges: number;
}

export interface GraphResponse extends GraphData {
  stats: GraphStats;
}

export interface ReasoningStep {
  source: string;
  relation: string;
  target: string;
  evidence: Evidence | null;
}

export interface QueryResponse {
  question: string;
  answer: string;
  matched_entities: string[];
  paths: ReasoningStep[][];
  highlighted_node_ids: string[];
  highlighted_edge_ids: string[];
  confidence: 'high' | 'medium' | 'low';
}

export interface DocumentUploadResponse {
  document_id: string;
  name: string;
  chunks: number;
  status: string;
}

export interface DocumentSummary {
  document_id: string;
  name: string;
  created_at: string;
}

export interface EntityDetail {
  entity: Entity;
  outgoing: Relationship[];
  incoming: Relationship[];
  neighbors: Entity[];
}

export interface HealthResponse {
  status: string;
  llm_enabled: boolean;
}

export type Selection = { kind: 'node'; id: string } | { kind: 'edge'; id: string } | null;

export interface Filters {
  types: Set<EntityType>;
  relations: Set<string>;
  minConfidence: number;
}
