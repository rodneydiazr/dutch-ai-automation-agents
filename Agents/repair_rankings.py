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

DATABASE_URL = os.getenv("DATABASE_URL")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing from .env")

if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is missing from .env")

client = Anthropic(api_key=ANTHROPIC_API_KEY)


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    return psycopg2.connect(DATABASE_URL)


# ============================================================
# FIND COMPANIES THAT STILL NEED RANKINGS
# ============================================================

def get_missing_companies():

    conn = get_connection()
    cur = conn.cursor()

    query = """
        SELECT
            c.id,
            c.name
        FROM companies c
        JOIN company_solutions s
            ON s.company_id = c.id
        LEFT JOIN final_rankings f
            ON f.company_id = c.id
        WHERE f.company_id IS NULL
        ORDER BY c.id;
    """

    cur.execute(query)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows


# ============================================================
# GET ALL AVAILABLE DATA FOR ONE COMPANY
# ============================================================

def get_company_data(company_id):

    conn = get_connection()
    cur = conn.cursor()

    result = {}

    # --------------------------------------------------------
    # Company
    # --------------------------------------------------------

    cur.execute(
        """
        SELECT *
        FROM companies
        WHERE id = %s
        """,
        (company_id,)
    )

    row = cur.fetchone()

    if row:
        columns = [desc[0] for desc in cur.description]
        result["company"] = dict(zip(columns, row))

    # --------------------------------------------------------
    # Research
    # --------------------------------------------------------

    cur.execute(
        """
        SELECT *
        FROM company_research
        WHERE company_id = %s
        """,
        (company_id,)
    )

    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]

    result["research"] = [
        dict(zip(columns, row))
        for row in rows
    ]

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    cur.execute(
        """
        SELECT *
        FROM company_validation
        WHERE company_id = %s
        """,
        (company_id,)
    )

    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]

    result["validation"] = [
        dict(zip(columns, row))
        for row in rows
    ]

    # --------------------------------------------------------
    # Solutions
    # --------------------------------------------------------

    cur.execute(
        """
        SELECT *
        FROM company_solutions
        WHERE company_id = %s
        """,
        (company_id,)
    )

    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]

    result["solutions"] = [
        dict(zip(columns, row))
        for row in rows
    ]

    cur.close()
    conn.close()

    return result


# ============================================================
# ASK CLAUDE TO RANK ONE COMPANY
# ============================================================

def rank_company(company_data):

    prompt = f"""
You are an AI automation consulting business analyst.

Evaluate this Dutch company as a potential customer for AI automation,
digital transformation, workflow automation, data automation, and
AI-agent solutions.

COMPANY DATA:
{json.dumps(company_data, indent=2, default=str)}

Return ONLY valid JSON.

Use exactly this structure:

{{
    "final_score": 0,
    "priority": "High",
    "opportunity_summary": "Short explanation of the opportunity.",
    "recommended_solution": "The most appropriate AI/automation solution.",
    "recommended_pitch": "A short sales pitch for this company.",
    "reasoning": "Why this company deserves this score."
}}

Rules:

- final_score must be an integer from 0 to 100.
- priority must be exactly one of:
  "High", "Medium", "Low"
- Be realistic.
- Do not invent facts that are not supported by the supplied data.
- Focus on actual business value.
- Consider automation potential, operational complexity,
  data needs, likely pain points, and implementation feasibility.
"""


    response = client.messages.create(
        model=MODEL,
        max_tokens=2500,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # Claude can return thinking blocks.
    # We only want actual text blocks.
    # --------------------------------------------------------

    text_parts = []

    for block in response.content:

        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)

    text = "\n".join(text_parts).strip()

    # --------------------------------------------------------
    # Remove markdown JSON fences if Claude adds them
    # --------------------------------------------------------

    if text.startswith("```"):
        text = text.replace("```json", "")
        text = text.replace("```", "")
        text = text.strip()

    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    try:
        return json.loads(text)

    except json.JSONDecodeError:

        # Try extracting the JSON object from surrounding text
        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1:

            json_text = text[start:end + 1]

            try:
                return json.loads(json_text)

            except json.JSONDecodeError:
                pass

        raise RuntimeError(
            f"Claude returned invalid JSON:\n{text}"
        )


# ============================================================
# SAVE ONE RANKING
# ============================================================

def save_ranking(company_id, company_name, ranking):

    conn = get_connection()
    cur = conn.cursor()

    # --------------------------------------------------------
    # Find the next available rank
    # --------------------------------------------------------

    cur.execute(
        """
        SELECT COALESCE(MAX(final_rank), 0)
        FROM final_rankings
        """
    )

    highest_rank = cur.fetchone()[0]

    next_rank = highest_rank + 1

    # --------------------------------------------------------
    # Insert
    # --------------------------------------------------------

    cur.execute(
        """
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
            ranked_by
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        """,
        (
            company_id,
            company_name,
            next_rank,
            ranking.get("priority"),
            ranking.get("final_score"),
            ranking.get("opportunity_summary"),
            ranking.get("recommended_solution"),
            ranking.get("recommended_pitch"),
            ranking.get("reasoning"),
            "Claude"
        )
    )

    conn.commit()

    cur.close()
    conn.close()

    return next_rank


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("RANKING REPAIR")
    print("=" * 60)

    missing = get_missing_companies()

    print()
    print(f"Companies missing final rankings: {len(missing)}")
    print()

    if not missing:
        print("Nothing to repair.")
        return

    print("Companies that will be processed:")
    print()

    for company_id, company_name in missing:
        print(f"{company_id}: {company_name}")

    print()
    print("=" * 60)

    for number, (company_id, company_name) in enumerate(missing, start=1):

        print()
        print(
            f"[{number}/{len(missing)}] "
            f"Ranking: {company_name}"
        )

        try:

            data = get_company_data(company_id)

            ranking = rank_company(data)

            score = ranking.get("final_score")

            priority = ranking.get("priority")

            print(
                f"Claude result: score={score}, "
                f"priority={priority}"
            )

            rank = save_ranking(
                company_id,
                company_name,
                ranking
            )

            print(
                f"SUCCESS -> inserted final rank {rank}"
            )

        except Exception as e:

            print()
            print(
                f"FAILED: {company_name}"
            )

            print(f"ERROR: {e}")

            print()
            print("Continuing with the next company...")

        # Small pause between API calls
        time.sleep(1)

    print()
    print("=" * 60)
    print("REPAIR FINISHED")
    print("=" * 60)

    # --------------------------------------------------------
    # Final verification
    # --------------------------------------------------------

    remaining = get_missing_companies()

    print()
    print(
        f"Companies still missing rankings: {len(remaining)}"
    )

    if remaining:

        print()
        for company_id, company_name in remaining:
            print(
                f"STILL MISSING: "
                f"{company_id} - {company_name}"
            )

    else:

        print()
        print("ALL COMPANIES WITH SOLUTIONS NOW HAVE RANKINGS.")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()