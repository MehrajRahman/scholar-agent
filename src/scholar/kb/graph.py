"""Neo4j GraphRAG store.

The graph is what stops the system recommending things a student can't get:
constraints (GPA / region / funding) are *traversals*, not vibes. The
matchmaking signal we read out is **graph proximity** — how many skill/topic
paths connect a Student to an Opportunity:

    (Student)-[:HAS_SKILL]->(Skill)<-[:REQUIRES]-(Opportunity)
    (Student)-[:INTERESTED_IN]->(Topic)<-[:RESEARCHES]-(Professor)-[:OFFERS]->(Opportunity)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from neo4j import AsyncGraphDatabase

from ..config import get_settings
from ..observability import get_logger
from ..schemas import Opportunity, StudentProfile

log = get_logger("graph")


class GraphStore:
    def __init__(self) -> None:
        s = get_settings()
        self._driver = AsyncGraphDatabase.driver(
            s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password)
        )

    async def close(self) -> None:
        await self._driver.close()

    async def upsert_student(self, p: StudentProfile) -> None:
        await self._driver.execute_query(
            """
            MERGE (s:Student {email: coalesce($email, $name)})
            SET s.name = $name, s.target_degree = $target,
                s.gpa_4 = $gpa, s.requires_funding = $funding,
                s.regions = $regions
            WITH s
            UNWIND $skills AS skill
              MERGE (sk:Skill {name: toLower(skill)})
              MERGE (s)-[:HAS_SKILL]->(sk)
            WITH s
            UNWIND $interests AS topic
              MERGE (t:Topic {name: toLower(topic)})
              MERGE (s)-[:INTERESTED_IN]->(t)
            """,
            email=p.email,
            name=p.full_name,
            target=p.target_degree,
            gpa=p.best_gpa_4,
            funding=p.requires_full_funding,
            regions=p.geographic_constraints,
            skills=p.skills,
            interests=p.research_interests,
        )

    async def upsert_opportunity(self, o: Opportunity) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._driver.execute_query(
            """
            MERGE (op:Opportunity {id: $id})
            ON CREATE SET op.first_seen_at = $now, op.version = 1
            ON MATCH SET op.version = CASE
                  WHEN op.content_hash <> $hash THEN coalesce(op.version, 1) + 1
                  ELSE coalesce(op.version, 1) END
            SET op.title = $title, op.kind = $kind, op.min_gpa_4 = $min_gpa,
                op.fully_funded = $funded, op.regions = $regions,
                op.deadline = $deadline, op.source_url = $url,
                op.content_hash = $hash, op.last_verified_at = $now,
                op.status = 'active'
            MERGE (u:University {name: coalesce($university, 'Unknown')})
            MERGE (op)-[:AT]->(u)
            WITH op
            UNWIND $skills AS skill
              MERGE (sk:Skill {name: toLower(skill)})
              MERGE (op)-[:REQUIRES]->(sk)
            WITH op
            FOREACH (_ IN CASE WHEN $prof_name IS NULL THEN [] ELSE [1] END |
              MERGE (pr:Professor {name: $prof_name})
              SET pr.email = $prof_email, pr.summary = $prof_summary
              MERGE (pr)-[:OFFERS]->(op)
            )
            """,
            id=o.id,
            now=now,
            hash=o.content_hash,
            title=o.title,
            kind=o.kind.value,
            min_gpa=o.min_gpa_4,
            funded=o.funding.is_fully_funded,
            regions=o.eligible_regions,
            deadline=o.deadline,
            url=o.source_url,
            university=o.university,
            skills=o.required_skills,
            prof_name=o.professor.name if o.professor else None,
            prof_email=o.professor.email if o.professor else None,
            prof_summary=o.professor.research_summary if o.professor else None,
        )

    async def expire_sweep(self, stale_ttl_days: int = 21) -> dict[str, int]:
        """Lifecycle maintenance: expire past-deadline offers, mark unverified
        ones stale. Run after deep research and on the n8n nightly cron."""
        today = date.today().isoformat()
        stale_before = (
            datetime.now(timezone.utc) - timedelta(days=stale_ttl_days)
        ).isoformat()
        records, _, _ = await self._driver.execute_query(
            """
            MATCH (op:Opportunity)
            WITH op, CASE
                WHEN op.deadline IS NOT NULL AND op.deadline < $today THEN 'expired'
                WHEN op.last_verified_at IS NOT NULL AND op.last_verified_at < $stale_before
                    THEN 'stale'
                ELSE coalesce(op.status, 'active') END AS new_status
            SET op.status = new_status
            RETURN op.status AS status, count(*) AS n
            """,
            today=today,
            stale_before=stale_before,
        )
        return {r["status"]: r["n"] for r in records}

    async def eligible(self, student: StudentProfile, opp_id: str) -> bool:
        """Hard-constraint gate evaluated in the graph (GPA / region / funding)."""
        records, _, _ = await self._driver.execute_query(
            """
            MATCH (s:Student {email: $email}), (op:Opportunity {id: $opp})
            RETURN
              (op.min_gpa_4 IS NULL OR s.gpa_4 IS NULL OR s.gpa_4 >= op.min_gpa_4) AS gpa_ok,
              (NOT s.requires_funding OR op.fully_funded) AS funding_ok,
              (size(s.regions) = 0 OR size(op.regions) = 0
                 OR any(r IN s.regions WHERE r IN op.regions)) AS region_ok
            """,
            email=student.email or student.full_name,
            opp=opp_id,
        )
        if not records:
            return False
        r = records[0]
        return bool(r["gpa_ok"] and r["funding_ok"] and r["region_ok"])

    async def graph_proximity(self, student: StudentProfile, opp_id: str) -> float:
        """Normalised count of skill/topic paths linking student -> opportunity."""
        records, _, _ = await self._driver.execute_query(
            """
            MATCH (s:Student {email: $email}), (op:Opportunity {id: $opp})
            OPTIONAL MATCH (s)-[:HAS_SKILL]->(sk:Skill)<-[:REQUIRES]-(op)
            WITH s, op, count(DISTINCT sk) AS shared_skills
            OPTIONAL MATCH (op)-[:REQUIRES]->(req:Skill)
            WITH shared_skills, count(DISTINCT req) AS total_req
            RETURN shared_skills,
                   CASE WHEN total_req = 0 THEN 0.0
                        ELSE toFloat(shared_skills) / total_req END AS coverage
            """,
            email=student.email or student.full_name,
            opp=opp_id,
        )
        if not records:
            return 0.0
        return float(records[0]["coverage"])

    async def professor_record(self, opp_id: str) -> dict | None:
        """Ground-truth professor data the Quality Gate validates citations against."""
        records, _, _ = await self._driver.execute_query(
            """
            MATCH (pr:Professor)-[:OFFERS]->(op:Opportunity {id: $opp})
            RETURN pr.name AS name, pr.email AS email, pr.summary AS summary
            LIMIT 1
            """,
            opp=opp_id,
        )
        return dict(records[0]) if records else None


@lru_cache
def get_graph() -> GraphStore:
    return GraphStore()
