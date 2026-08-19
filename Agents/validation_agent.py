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
# GET RESEARCH
# ============================================================

def get_company_research():

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
                cr.evidence,
                cr.automation_score
            FROM companies c
            INNER JOIN company_research cr
                ON c.id = cr.company_id
            ORDER BY c.id
            LIMIT %s
            """,
            (TEST_LIMIT,)
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ============================================================
# VALIDATE OPPORTUNITY
# ============================================================

def validate_company(company):

    (
        company_id,
        name,
        website,
        industry,
        location,
        company_summary,
        automation_opportunities,
        evidence,
        automation_score
    ) = company

    print()
    print("-" * 60)
    print(f"Validating: {name}")
    print("-" * 60)

    research = {
        "company_summary": company_summary,
        "automation_opportunities":
            automation_opportunities,
        "evidence": evidence,
        "automation_score":
            automation_score
    }

    research_text = json.dumps(
        research,
        ensure_ascii=False,
        indent=2,
        default=str
    )

    schema = {
        "type": "object",
        "properties": {
            "is_valid_opportunity": {
                "type": "boolean"
            },
            "validation_score": {
                "type": "integer"
            },
            "business_need": {
                "type": "string"
            },
            "pain_points": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "automation_feasibility": {
                "type": "string"
            },
            "reasoning": {
                "type": "string"
            },
            "priority": {
                "type": "string",
                "enum": [
                    "high",
                    "medium",
                    "low",
                    "not_viable"
                ]
            }
        },
        "required": [
            "is_valid_opportunity",
            "validation_score",
            "business_need",
            "pain_points",
            "automation_feasibility",
            "reasoning",
            "priority"
        ],
        "additionalProperties": False
    }

    prompt = f"""
You are Agent 3 in a five-agent AI automation consulting
system.

Your job is to validate whether the company below represents
a realistic business opportunity for AI automation consulting.

COMPANY:

Name: {name}
Website: {website}
Industry: {industry}
Location: {location}

RESEARCH FROM AGENT 2:

{research_text}

Evaluate the opportunity based on:

1. Is there a genuine business problem?
2. Is the problem likely to involve repetitive,
   administrative, information-heavy, or inefficient work?
3. Could AI or automation realistically improve it?
4. Is there enough evidence to justify approaching the company?
5. Would solving the problem potentially create meaningful
   business value?
6. Is the proposed opportunity realistic rather than
   speculative?

Be conservative.

Do NOT assume a company has a problem simply because AI could
theoretically be used.

Do NOT invent facts.

A company should only receive a HIGH priority when there is
strong evidence of a meaningful automation opportunity.

Return:

- is_valid_opportunity
- validation_score from 0-100
- business_need
- pain_points
- automation_feasibility
- reasoning
- priority

Priority definitions:

HIGH:
Strong evidence and strong potential business value.

MEDIUM:
Reasonable opportunity but evidence or value is less certain.

LOW:
Possible opportunity but weak evidence or limited value.

NOT_VIABLE:
Insufficient evidence or unrealistic opportunity.

Return only the requested structured JSON.
"""

    response = claude.messages.create(
        model=MODEL,
        max_tokens=6000,
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
# SAVE VALIDATION
# ============================================================

def save_validation(
    company_id,
    validation
):

    connection = psycopg2.connect(
        DATABASE_URL
    )

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            DELETE FROM company_validation
            WHERE company_id = %s
            """,
            (company_id,)
        )

        cursor.execute(
            """
            INSERT INTO company_validation
            (
                company_id,
                is_valid_opportunity,
                validation_score,
                business_need,
                pain_points,
                automation_feasibility,
                reasoning,
                priority,
                validated_by
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s::jsonb,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                company_id,
                validation[
                    "is_valid_opportunity"
                ],
                validation[
                    "validation_score"
                ],
                validation[
                    "business_need"
                ],
                json.dumps(
                    validation[
                        "pain_points"
                    ]
                ),
                validation[
                    "automation_feasibility"
                ],
                validation[
                    "reasoning"
                ],
                validation[
                    "priority"
                ],
                "agent_3_validation"
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
    print("AGENT 3 - OPPORTUNITY VALIDATION")
    print("=" * 60)

    companies = get_company_research()

    print()
    print(
        f"Companies to validate: "
        f"{len(companies)}"
    )

    successful = 0
    failed = 0

    for company in companies:

        try:

            validation = validate_company(
                company
            )

            save_validation(
                company[0],
                validation
            )

            successful += 1

            print(
                f"SUCCESS: {company[1]} "
                f"| Score: "
                f"{validation['validation_score']} "
                f"| Priority: "
                f"{validation['priority']}"
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
    print("AGENT 3 COMPLETE")
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

