import os
import json
import time
import psycopg2
from dotenv import load_dotenv
from anthropic import Anthropic


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

MAX_COMPANIES = 50
BATCH_SIZE = 5
MAX_RETRIES = 3
API_DELAY = 1


if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is missing from .env")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing from .env")

client = Anthropic(api_key=ANTHROPIC_API_KEY)


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    return psycopg2.connect(DATABASE_URL)


# ============================================================
# LOAD COMPLETE COMPANIES WITHOUT FINAL RANKINGS
# ============================================================

def get_complete_companies():

    conn = get_connection()
    cur = conn.cursor()

    query = """
        SELECT
            c.id AS company_id,
            c.name AS company_name,
            c.website,
            c.industry,
            c.location,
            c.employee_estimate,
            c.description,
            c.source_url,

            r.research_data,
            v.validation_data,
            s.solution_data

        FROM companies c

        INNER JOIN LATERAL (
            SELECT to_jsonb(cr.*) AS research_data
            FROM company_research cr
            WHERE cr.company_id = c.id
            ORDER BY cr.id DESC
            LIMIT 1
        ) r ON TRUE

        INNER JOIN LATERAL (
            SELECT to_jsonb(cv.*) AS validation_data
            FROM company_validation cv
            WHERE cv.company_id = c.id
            ORDER BY cv.id DESC
            LIMIT 1
        ) v ON TRUE

        INNER JOIN LATERAL (
            SELECT to_jsonb(cs.*) AS solution_data
            FROM company_solutions cs
            WHERE cs.company_id = c.id
            ORDER BY cs.id DESC
            LIMIT 1
        ) s ON TRUE

        LEFT JOIN final_rankings f
            ON f.company_id = c.id

        WHERE f.company_id IS NULL

        ORDER BY c.id
        LIMIT %s;
    """

    cur.execute(query, (MAX_COMPANIES,))
    rows = cur.fetchall()

    columns = [
        "company_id",
        "company_name",
        "website",
        "industry",
        "location",
        "employee_estimate",
        "description",
        "source_url",
        "research_data",
        "validation_data",
        "solution_data",
    ]

    records = [
        dict(zip(columns, row))
        for row in rows
    ]

    cur.close()
    conn.close()

    return records


# ============================================================
# CLAUDE OUTPUT SCHEMA
# ============================================================

RANKING_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "company_id": {
                "type": "integer"
            },
            "score": {
                "type": "integer"
            },
            "priority": {
                "type": "string",
                "enum": [
                    "High",
                    "Medium",
                    "Low"
                ]
            },
            "summary": {
                "type": "string"
            },
            "recommended_solution": {
                "type": "string"
            },
            "recommended_pitch": {
                "type": "string"
            },
            "reasoning": {
                "type": "string"
            }
        },
        "required": [
            "company_id",
            "score",
            "priority",
            "summary",
            "recommended_solution",
            "recommended_pitch",
            "reasoning"
        ],
        "additionalProperties": False
    }
}


# ============================================================
# RANK ONE BATCH
# ============================================================

def rank_batch(records):

    companies = []

    for record in records:

        companies.append({
            "company_id": record["company_id"],
            "company_name": record["company_name"],
            "website": record["website"],
            "industry": record["industry"],
            "location": record["location"],
            "employee_estimate": record["employee_estimate"],
            "description": record["description"],
            "research": record["research_data"],
            "validation": record["validation_data"],
            "solution": record["solution_data"],
        })

    prompt = f"""
You are the final ranking agent for a Dutch B2B AI automation
consulting business.

Evaluate each company as a potential customer.

Consider:

1. Strength of the business pain
2. Evidence supporting the pain
3. Quality of the validated opportunity
4. Quality of the proposed AI/automation solution
5. Potential business value
6. Implementation feasibility
7. Likelihood the company could realistically buy
8. Overall attractiveness as a sales opportunity

Score each company from 0 to 100.

Scoring:

90-100 = exceptional
80-89  = very strong
70-79  = strong
60-69  = reasonable
50-59  = weak
0-49   = poor

Be commercially realistic.

Do not invent facts.

Return EXACTLY ONE result for every company supplied.

COMPANIES:

{json.dumps(companies, indent=2, default=str)}
"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=10000,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": RANKING_SCHEMA
            }
        }
    )

    text_parts = []

    for block in response.content:

        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)

    if not text_parts:
        raise RuntimeError(
            "Claude returned no text output."
        )

    text = "\n".join(text_parts).strip()

    try:
        rankings = json.loads(text)

    except json.JSONDecodeError as e:

        print("\nClaude returned:")
        print(text)

        raise RuntimeError(
            f"Invalid JSON returned by Claude: {e}"
        )

    if not isinstance(rankings, list):
        raise RuntimeError(
            "Claude output was not a list."
        )

    return rankings


# ============================================================
# VALIDATE CLAUDE RESULTS
# ============================================================

def validate_results(rankings, records):

    expected_ids = {
        r["company_id"]
        for r in records
    }

    returned_ids = {
        r["company_id"]
        for r in rankings
    }

    missing = expected_ids - returned_ids
    unexpected = returned_ids - expected_ids

    if unexpected:
        print(
            f"WARNING: Claude returned "
            f"{len(unexpected)} unexpected IDs."
        )

    if missing:
        print(
            f"WARNING: Claude missed "
            f"{len(missing)} companies in this batch."
        )

    clean = []

    for ranking in rankings:

        company_id = ranking["company_id"]

        if company_id not in expected_ids:
            continue

        score = int(ranking["score"])

        score = max(0, min(100, score))

        ranking["score"] = score

        clean.append(ranking)

    return clean


# ============================================================
# SAVE RESULTS
# ============================================================

def save_results(rankings, company_lookup):

    conn = get_connection()
    cur = conn.cursor()

    for ranking in rankings:

        company_id = ranking["company_id"]

        company_name = company_lookup.get(
            company_id,
            "Unknown Company"
        )

        query = """
            INSERT INTO final_rankings (
                company_id,
                company_name,
                final_rank,
                priority,
                final_score,
                opportunity_summary,
                recommended_solution,
                recommended_pitch,
                reasoning,
                ranked_by,
                created_at
            )

            VALUES (
                %s,
                %s,
                NULL,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                CURRENT_TIMESTAMP
            )

            ON CONFLICT (company_id)

            DO UPDATE SET
                company_name = EXCLUDED.company_name,
                priority = EXCLUDED.priority,
                final_score = EXCLUDED.final_score,
                opportunity_summary = EXCLUDED.opportunity_summary,
                recommended_solution = EXCLUDED.recommended_solution,
                recommended_pitch = EXCLUDED.recommended_pitch,
                reasoning = EXCLUDED.reasoning,
                ranked_by = EXCLUDED.ranked_by,
                created_at = CURRENT_TIMESTAMP;
        """

        cur.execute(
            query,
            (
                company_id,
                company_name,
                ranking["priority"],
                ranking["score"],
                ranking["summary"],
                ranking["recommended_solution"],
                ranking["recommended_pitch"],
                ranking["reasoning"],
                "Claude"
            )
        )

    conn.commit()

    cur.close()
    conn.close()


# ============================================================
# REBUILD FINAL RANK NUMBERS
# ============================================================

def rebuild_rank_numbers():

    conn = get_connection()
    cur = conn.cursor()

    query = """
        WITH ranked AS (
            SELECT
                company_id,
                ROW_NUMBER() OVER (
                    ORDER BY final_score DESC, company_id
                ) AS new_rank
            FROM final_rankings
        )

        UPDATE final_rankings fr
        SET final_rank = ranked.new_rank
        FROM ranked
        WHERE fr.company_id = ranked.company_id;
    """

    cur.execute(query)

    conn.commit()

    cur.close()
    conn.close()


# ============================================================
# VERIFY RESULTS
# ============================================================

def verify_results():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT COUNT(*)
        FROM final_rankings
        """
    )

    total = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM final_rankings
        WHERE final_score IS NOT NULL
        """
    )

    scored = cur.fetchone()[0]

    cur.execute(
        """
        SELECT
            c.id,
            c.name
        FROM companies c
        INNER JOIN company_research r
            ON r.company_id = c.id
        INNER JOIN company_validation v
            ON v.company_id = c.id
        INNER JOIN company_solutions s
            ON s.company_id = c.id
        LEFT JOIN final_rankings f
            ON f.company_id = c.id
        WHERE f.company_id IS NULL
        ORDER BY c.id;
        """
    )

    missing = cur.fetchall()

    cur.close()
    conn.close()

    return total, scored, missing


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("FINAL RANKING AGENT")
    print("=" * 70)

    print("\nLoading complete companies without final rankings...")

    records = get_complete_companies()

    print(
        f"Complete companies available: {len(records)}"
    )

    if not records:

        print(
            "\nNo unranked complete companies found."
        )

        return

    company_lookup = {
        r["company_id"]: r["company_name"]
        for r in records
    }

    all_rankings = []

    total_batches = (
        len(records) + BATCH_SIZE - 1
    ) // BATCH_SIZE

    print(
        f"\nProcessing {len(records)} companies "
        f"in {total_batches} batches."
    )

    for start in range(
        0,
        len(records),
        BATCH_SIZE
    ):

        batch = records[
            start:start + BATCH_SIZE
        ]

        batch_number = (
            start // BATCH_SIZE
        ) + 1

        print(
            f"\nBATCH {batch_number}/{total_batches}"
        )

        print(
            "Companies:"
        )

        for record in batch:
            print(
                f"  - {record['company_name']}"
            )

        success = False

        for attempt in range(
            1,
            MAX_RETRIES + 1
        ):

            try:

                rankings = rank_batch(batch)

                rankings = validate_results(
                    rankings,
                    batch
                )

                if len(rankings) != len(batch):

                    raise RuntimeError(
                        f"Claude returned "
                        f"{len(rankings)} of "
                        f"{len(batch)} expected rankings."
                    )

                all_rankings.extend(rankings)

                print(
                    f"SUCCESS: "
                    f"{len(rankings)}/{len(batch)}"
                )

                success = True

                break

            except Exception as e:

                print(
                    f"Attempt {attempt}/"
                    f"{MAX_RETRIES} failed:"
                )

                print(e)

                if attempt < MAX_RETRIES:

                    print(
                        "Retrying in 5 seconds..."
                    )

                    time.sleep(5)

        if not success:

            raise RuntimeError(
                f"Batch {batch_number} failed "
                f"after {MAX_RETRIES} attempts."
            )

        time.sleep(API_DELAY)

    # --------------------------------------------------------
    # REMOVE DUPLICATES
    # --------------------------------------------------------

    unique = {}

    for ranking in all_rankings:

        unique[
            ranking["company_id"]
        ] = ranking

    all_rankings = list(
        unique.values()
    )

    print(
        f"\nGenerated rankings: "
        f"{len(all_rankings)}"
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    print("\nSaving rankings to Neon...")

    save_results(
        all_rankings,
        company_lookup
    )

    # --------------------------------------------------------
    # RECALCULATE RANKS
    # --------------------------------------------------------

    print(
        "Rebuilding final rank numbers..."
    )

    rebuild_rank_numbers()

    # --------------------------------------------------------
    # VERIFY
    # --------------------------------------------------------

    total, scored, missing = verify_results()

    print("\n" + "=" * 70)
    print("FINAL VERIFICATION")
    print("=" * 70)

    print(
        f"Rows in final_rankings: {total}"
    )

    print(
        f"Rows with scores: {scored}"
    )

    print(
        f"Complete companies still missing: "
        f"{len(missing)}"
    )

    if missing:

        print("\nStill missing:")

        for company_id, name in missing:

            print(
                f"  {company_id}: {name}"
            )

    else:

        print(
            "\nSUCCESS: Every complete company "
            "has a final ranking."
        )

    print("\nTOP 10:")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            final_rank,
            company_name,
            final_score,
            priority
        FROM final_rankings
        ORDER BY final_rank
        LIMIT 10;
        """
    )

    for rank, name, score, priority in cur.fetchall():

        print(
            f"{rank:2}. "
            f"{name[:40]:40} "
            f"{score:3}/100 "
            f"{priority}"
        )

    cur.close()
    conn.close()

    print("\nDONE.")


if __name__ == "__main__":
    main()
