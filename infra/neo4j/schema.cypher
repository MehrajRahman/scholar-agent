// ============================================================================
// scholar-agent — Neo4j GraphRAG schema  (Deliverable #2)
// Run once at bootstrap:  cypher-shell -f infra/neo4j/schema.cypher
// Neo4j 5.x (uses native vector indexes).
// ============================================================================

// --- Node graph data model --------------------------------------------------
//
//   (Student)-[:HAS_SKILL]------>(Skill)<-----[:REQUIRES]-(Opportunity)
//   (Student)-[:INTERESTED_IN]-->(Topic)<-----[:RESEARCHES]-(Professor)
//   (Professor)-[:OFFERS]------->(Opportunity)-[:AT]------>(University)
//   (Professor)-[:AFFILIATED_WITH]->(University)
//   (Opportunity)-[:FUNDED_BY]-->(Funding)
//
// This lets the Matchmaker answer "is the student qualified AND aligned?" as a
// graph traversal instead of trusting an LLM's say-so.

// --- Uniqueness constraints (also create backing indexes) -------------------
CREATE CONSTRAINT student_email      IF NOT EXISTS FOR (s:Student)      REQUIRE s.email IS UNIQUE;
CREATE CONSTRAINT opportunity_id     IF NOT EXISTS FOR (o:Opportunity)  REQUIRE o.id IS UNIQUE;
CREATE CONSTRAINT university_name    IF NOT EXISTS FOR (u:University)    REQUIRE u.name IS UNIQUE;
CREATE CONSTRAINT professor_name     IF NOT EXISTS FOR (p:Professor)    REQUIRE p.name IS UNIQUE;
CREATE CONSTRAINT skill_name         IF NOT EXISTS FOR (sk:Skill)       REQUIRE sk.name IS UNIQUE;
CREATE CONSTRAINT topic_name         IF NOT EXISTS FOR (t:Topic)        REQUIRE t.name IS UNIQUE;
CREATE CONSTRAINT funding_id         IF NOT EXISTS FOR (f:Funding)      REQUIRE f.id IS UNIQUE;

// --- Property indexes for the hard-constraint filters -----------------------
CREATE INDEX opportunity_deadline    IF NOT EXISTS FOR (o:Opportunity)  ON (o.deadline);
CREATE INDEX opportunity_kind        IF NOT EXISTS FOR (o:Opportunity)  ON (o.kind);
CREATE INDEX opportunity_funded      IF NOT EXISTS FOR (o:Opportunity)  ON (o.fully_funded);
// Freshness lifecycle (drives the expire-sweep + nightly refresh).
CREATE INDEX opportunity_status      IF NOT EXISTS FOR (o:Opportunity)  ON (o.status);
CREATE INDEX opportunity_verified    IF NOT EXISTS FOR (o:Opportunity)  ON (o.last_verified_at);

// --- Vector index: GraphRAG over opportunity embeddings ---------------------
// Lets you do semantic search *inside* Cypher (db.index.vector.queryNodes),
// fusing graph hops with dense similarity. Dim must match EMBED_MODEL
// (bge-large-en-v1.5 -> 1024). Qdrant is the primary ANN store; this mirror
// enables single-query GraphRAG when you want graph + vector in one place.
CREATE VECTOR INDEX opportunity_embedding IF NOT EXISTS
FOR (o:Opportunity) ON (o.embedding)
OPTIONS { indexConfig: { `vector.dimensions`: 1024, `vector.similarity_function`: 'cosine' } };
