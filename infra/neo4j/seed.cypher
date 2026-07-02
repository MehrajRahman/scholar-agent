// ============================================================================
// Demo seed data — a tiny graph so you can eyeball the model / run queries
// before the live Scout has populated anything. Idempotent (MERGE-based).
// Run:  cypher-shell -f infra/neo4j/seed.cypher
// ============================================================================

// --- A sample applicant -----------------------------------------------------
MERGE (s:Student {email: 'ada@example.com'})
  SET s.name = 'Ada Researcher', s.target_degree = 'PhD',
      s.gpa_4 = 3.8, s.requires_funding = true, s.regions = ['Germany', 'Netherlands'];

UNWIND ['machine learning', 'graph neural networks', 'python'] AS skill
  MERGE (sk:Skill {name: skill})
  MERGE (s)-[:HAS_SKILL]->(sk);

UNWIND ['drug discovery', 'graph representation learning'] AS topic
  MERGE (t:Topic {name: topic})
  MERGE (s)-[:INTERESTED_IN]->(t);

// --- A university + professor + funded PhD position -------------------------
MERGE (u:University {name: 'TU Delft'})
MERGE (p:Professor {name: 'Dr. Jane Liu'})
  SET p.email = 'j.liu@tudelft.nl',
      p.summary = 'Publishes on: graph neural networks, molecular property prediction, drug discovery'
MERGE (p)-[:AFFILIATED_WITH]->(u);

MERGE (o:Opportunity {id: 'seed-phd-001'})
  SET o.title = 'Funded PhD: GNNs for Drug Discovery',
      o.kind = 'phd_position', o.min_gpa_4 = 3.5,
      o.fully_funded = true, o.regions = ['Netherlands'],
      o.deadline = '2026-09-01',
      o.source_url = 'https://example.edu/phd/gnn-drug-discovery'
MERGE (o)-[:AT]->(u)
MERGE (p)-[:OFFERS]->(o);

UNWIND ['machine learning', 'graph neural networks'] AS rs
  MERGE (sk:Skill {name: rs})
  MERGE (o)-[:REQUIRES]->(sk);

MERGE (f:Funding {id: 'seed-fund-001'})
  SET f.source = 'NWO', f.is_fully_funded = true, f.covers_tuition = true
MERGE (o)-[:FUNDED_BY]->(f);

// --- Sanity query: shared-skill coverage between Ada and the seeded PhD ------
// MATCH (s:Student {email:'ada@example.com'})-[:HAS_SKILL]->(sk)<-[:REQUIRES]-(o:Opportunity)
// RETURN o.title, collect(sk.name) AS shared_skills;
