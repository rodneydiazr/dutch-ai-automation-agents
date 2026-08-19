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

MODEL = "claude-sonnet-5"

TEST_LIMIT = 5


# ============================================================
# CHECK ENVIRONMENT
# ============================================================

if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is missing from .env")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing from .env")


# ============================================================
# CLAUDE CLIENT
# ============================================================

claude = Anthropic(
    api_key=ANTHROPIC_API_KEY
)


# ============================================================
# GET VALIDATED COMPANIES WITHOUT SOLUTIONS
# ============================================================

def get_validated_companies():

    connection = psycopg2.connect(
        DATABASE_URL
    )

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            SELECT
                c.id,
                c.name,
                c.website,
                c.industry,
                c.location,
                cr.company_summary,
                cr.automation_opportunities,
                cv.is_valid_opportunity,
                cv.validation_score,
                cv.business_need,
                cv.pain_points,
                cv.automation_feasibility,
                cv.reasoning,
                cv.priority

            FROM companies c

            INNER JOIN company_research cr
                ON c.id = cr.company_id

            INNER JOIN company_validation cv
                ON c.id = cv.company_id

            LEFT JOIN company_solutions cs
                ON c.id = cs.company_id

            WHERE cv.is_valid_opportunity = TRUE
              AND cs.company_id IS NULL

            ORDER BY cv.validation_score DESC

            LIMIT %s
            """,
            (TEST_LIMIT,)
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ============================================================
# DESIGN SOLUTION
# ============================================================

def design_solution(company):

    (
        company_id,
        name,
        website,
        industry,
        location,
        company_summary,
        automation_opportunities,
        is_valid_opportunity,
        validation_score,
        business_need,
        pain_points,
        automation_feasibility,
        reasoning,
        priority
    ) = company

    print()
    print("-" * 60)
    print(f"Designing solution for: {name}")
    print("-" * 60)

    company_context = {
        "company_name": name,
        "website": website,
        "industry": industry,
        "location": location,
        "company_summary": company_summary,
        "automation_opportunities":
            automation_opportunities,
        "validation_score":
            validation_score,
        "business_need":
            business_need,
        "pain_points":
            pain_points,
        "automation_feasibility":
            automation_feasibility,
        "validation_reasoning":
            reasoning,
        "priority":
            priority
    }

    context_text = json.dumps(
        company_context,
        ensure_ascii=False,
        indent=2,
        default=str
    )

    schema = {
        "type": "object",
        "properties": {
            "solution_name": {
                "type": "string"
            },
            "solution_summary": {
                "type": "string"
            },
            "business_problem": {
                "type": "string"
            },
            "how_it_works": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "ai_components": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "automation_components": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "data_requirements": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "technology_stack": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "expected_benefits": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "implementation_difficulty": {
                "type": "string",
                "enum": [
                    "low",
                    "medium",
                    "high"
                ]
            },
            "estimated_business_value": {
                "type": "integer"
            },
            "recommended_next_step": {
                "type": "string"
            }
        },
        "required": [
            "solution_name",
            "solution_summary",
            "business_problem",
            "how_it_works",
            "ai_components",
            "automation_components",
            "data_requirements",
            "technology_stack",
            "expected_benefits",
            "implementation_difficulty",
            "estimated_business_value",
            "recommended_next_step"
        ],
        "additionalProperties": False
    }

    prompt = f"""
You are Agent 4 in a five-agent AI automation consulting system.

Your job is to act as a senior AI solutions consultant.

You have received research and validation information about a
Dutch construction company.

Your task is to design ONE realistic AI automation solution that
could actually be proposed to this company.

COMPANY INFORMATION:

{context_text}

IMPORTANT:

Do NOT invent company facts.

Do NOT propose generic "AI transformation".

The solution must directly address the validated business need
and pain points.

The solution should be realistic for a consulting company to
build using technologies such as:

- Python
- APIs
- LLMs
- RAG
- PostgreSQL
- workflow automation
- document processing
- dashboards
- email automation
- internal knowledge assistants
- AI agents

You may recommend technologies when appropriate, but do not
assume the company already uses them.

Design a solution that could become a real consulting proposal.

Explain:

1. The exact problem.
2. The proposed AI solution.
3. How the workflow operates.
4. What AI components are needed.
5. What automation components are needed.
6. What data the solution needs.
7. A realistic technology stack.
8. Expected business benefits.
9. Implementation difficulty.
10. Estimated business value from 0-100.
11. The recommended next step with the client.

Be practical rather than futuristic.

Return only the requested structured JSON.
"""

    response = claude.messages.create(
        model=MODEL,
        max_tokens=8000,
        thinking={
            "type": "disabled"
        },
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": schema
            }
        }
    )

    text_parts = []

    for block in response.content:

        if getattr(block, "type", None) == "text":

            text = getattr(
                block,
                "text",
                None
            )

            if text:

                text_parts.append(text)

    if not text_parts:

        raise RuntimeError(
            "Claude returned no text."
        )

    text = "\n".join(
        text_parts
    ).strip()

    try:

        return json.loads(text)

    except json.JSONDecodeError as error:

        print()
        print("RAW CLAUDE RESPONSE:")
        print(text)
        print()

        raise RuntimeError(
            f"Invalid JSON from Claude: {error}"
        )


# ============================================================
# SAVE SOLUTION
# ============================================================

def save_solution(
    company_id,
    solution
):

    connection = psycopg2.connect(
        DATABASE_URL
    )

    cursor = connection.cursor()

    try:

        DELETE_SQL = """
            DELETE FROM company_solutions
            WHERE company_id = %s
        """

        cursor.execute(
            DELETE_SQL,
            (company_id,)
        )

        cursor.execute(
            """
            INSERT INTO company_solutions
            (
                company_id,
                solution_name,
                solution_summary,
                business_problem,
                how_it_works,
                ai_components,
                automation_components,
                data_requirements,
                technology_stack,
                expected_benefits,
                implementation_difficulty,
                estimated_business_value,
                recommended_next_step,
                designed_by
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s::jsonb,
                %s::jsonb,
                %s::jsonb,
                %s::jsonb,
                %s::jsonb,
                %s::jsonb,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                company_id,
                solution[
                    "solution_name"
                ],
                solution[
                    "solution_summary"
                ],
                solution[
                    "business_problem"
                ],
                json.dumps(
                    solution[
                        "how_it_works"
                    ]
                ),
                json.dumps(
                    solution[
                        "ai_components"
                    ]
                ),
                json.dumps(
                    solution[
                        "automation_components"
                    ]
                ),
                json.dumps(
                    solution[
                        "data_requirements"
                    ]
                ),
                json.dumps(
                    solution[
                        "technology_stack"
                    ]
                ),
                json.dumps(
                    solution[
                        "expected_benefits"
                    ]
                ),
                solution[
                    "implementation_difficulty"
                ],
                solution[
                    "estimated_business_value"
                ],
                solution[
                    "recommended_next_step"
                ],
                "agent_4_solution"
            )
        )

        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("AGENT 4 - AI SOLUTION DESIGN")
    print("=" * 60)

    companies = get_validated_companies()

    print()
    print(
        f"Validated companies to process: "
        f"{len(companies)}"
    )

    if not companies:

        print(
            "No validated companies without "
            "solutions found."
        )

        return

    successful = 0
    failed = 0

    for company in companies:

        try:

            solution = design_solution(
                company
            )

            save_solution(
                company[0],
                solution
            )

            successful += 1

            print(
                f"SUCCESS: {company[1]} "
                f"| Value: "
                f"{solution['estimated_business_value']}"
            )

        except Exception as error:

            failed += 1

            print()
            print(
                f"FAILED: {company[1]}"
            )

            print(error)

        time.sleep(0.5)

    print()
    print("=" * 60)
    print("AGENT 4 COMPLETE")
    print("=" * 60)

    print(
        f"Successful: {successful}"
    )

    print(
        f"Failed: {failed}"
    )

    print()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()