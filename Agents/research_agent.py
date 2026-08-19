import os
import json
import time
import psycopg2

from dotenv import load_dotenv
from anthropic import Anthropic
from tavily import TavilyClient


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

MODEL = "claude-sonnet-5"

# Run all companies
TEST_LIMIT = 5


# ============================================================
# CHECK ENVIRONMENT
# ============================================================

if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is missing from .env")

if not TAVILY_API_KEY:
    raise RuntimeError("TAVILY_API_KEY is missing from .env")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing from .env")


# ============================================================
# CLIENTS
# ============================================================

claude = Anthropic(
    api_key=ANTHROPIC_API_KEY
)

tavily = TavilyClient(
    api_key=TAVILY_API_KEY
)


# ============================================================
# DATABASE
# ============================================================

def get_companies():

    connection = psycopg2.connect(DATABASE_URL)
    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            SELECT
                id,
                name,
                website,
                industry,
                location,
                employee_estimate,
                description
            FROM companies
            ORDER BY id
            LIMIT %s
            """,
            (TEST_LIMIT,)
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ============================================================
# WEB RESEARCH
# ============================================================

def research_company(company):

    company_id = company[0]
    name = company[1]
    website = company[2]
    industry = company[3]
    location = company[4]
    employee_estimate = company[5]
    description = company[6]

    print()
    print("-" * 60)
    print(f"Researching: {name}")
    print("-" * 60)

    queries = [
        f'"{name}" Netherlands company',
        f'"{name}" construction projects Netherlands',
        f'"{name}" employees Netherlands',
        f'"{name}" technology digital transformation',
        f'"{name}" automation AI Netherlands'
    ]

    all_results = []

    for query in queries:

        try:

            results = tavily.search(
                query=query,
                search_depth="advanced",
                max_results=5
            )

            items = results.get(
                "results",
                []
            )

            all_results.extend(items)

        except Exception as error:

            print(
                f"Search error: {error}"
            )

    # Remove duplicate URLs
    unique_results = []
    seen_urls = set()

    for result in all_results:

        url = result.get("url")

        if url and url not in seen_urls:

            seen_urls.add(url)
            unique_results.append(result)

    print(
        f"Research sources found: "
        f"{len(unique_results)}"
    )

    return {
        "company_id": company_id,
        "name": name,
        "website": website,
        "industry": industry,
        "location": location,
        "employee_estimate": employee_estimate,
        "description": description,
        "sources": unique_results
    }


# ============================================================
# CLAUDE ANALYSIS
# ============================================================

def analyze_company(research):

    name = research["name"]

    sources = json.dumps(
        research["sources"],
        ensure_ascii=False,
        indent=2,
        default=str
    )

    schema = {
        "type": "object",
        "properties": {
            "official_website": {
                "type": ["string", "null"]
            },
            "company_summary": {
                "type": "string"
            },
            "automation_opportunities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "opportunity": {
                            "type": "string"
                        },
                        "reason": {
                            "type": "string"
                        },
                        "potential_impact": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "opportunity",
                        "reason",
                        "potential_impact"
                    ],
                    "additionalProperties": False
                }
            },
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {
                            "type": "string"
                        },
                        "source_url": {
                            "type": ["string", "null"]
                        }
                    },
                    "required": [
                        "claim",
                        "source_url"
                    ],
                    "additionalProperties": False
                }
            },
            "automation_score": {
                "type": "integer"
            }
        },
        "required": [
            "official_website",
            "company_summary",
            "automation_opportunities",
            "evidence",
            "automation_score"
        ],
        "additionalProperties": False
    }

    prompt = f"""
You are Agent 2 in a five-agent AI automation consulting system.

Your job is to deeply research the Dutch company:

COMPANY:
{name}

Existing information:

Website: {research["website"]}
Industry: {research["industry"]}
Location: {research["location"]}
Employees: {research["employee_estimate"]}
Description: {research["description"]}

Use ONLY the supplied web research as evidence.

Analyze:

1. What the company does.
2. Its size and business activities.
3. Its operations and workflows.
4. Signs of manual, repetitive, administrative or
   information-heavy processes.
5. Potential AI/automation opportunities.
6. Evidence supporting those opportunities.
7. A realistic automation opportunity score from 0-100.

IMPORTANT:

Do NOT invent facts.

Do NOT claim the company uses a technology unless the research
supports it.

Do NOT invent an official website.

Only include automation opportunities that are reasonably
supported by the company's business activities.

The automation score should reflect the potential for useful
AI/automation consulting, not how "advanced" the company is.

WEB RESEARCH:

{sources}
"""

    response = claude.messages.create(
        model=MODEL,
        max_tokens=10000,
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
# SAVE RESEARCH
# ============================================================

def save_research(company_id, analysis):

    connection = psycopg2.connect(
        DATABASE_URL
    )

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            DELETE FROM company_research
            WHERE company_id = %s
            """,
            (company_id,)
        )

        cursor.execute(
            """
            INSERT INTO company_research
            (
                company_id,
                official_website,
                company_summary,
                automation_opportunities,
                evidence,
                automation_score,
                researched_by
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s::jsonb,
                %s::jsonb,
                %s,
                %s
            )
            """,
            (
                company_id,
                analysis.get("official_website"),
                analysis.get("company_summary"),
                json.dumps(
                    analysis.get(
                        "automation_opportunities",
                        []
                    )
                ),
                json.dumps(
                    analysis.get(
                        "evidence",
                        []
                    )
                ),
                analysis.get(
                    "automation_score",
                    0
                ),
                "agent_2_research"
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
    print("AGENT 2 - COMPANY RESEARCH")
    print("=" * 60)

    companies = get_companies()

    print()
    print(
        f"Companies to research: "
        f"{len(companies)}"
    )

    successful = 0
    failed = 0

    for company in companies:

        try:

            research = research_company(
                company
            )

            analysis = analyze_company(
                research
            )

            save_research(
                company[0],
                analysis
            )

            successful += 1

            print(
                f"SUCCESS: {company[1]}"
            )

        except Exception as error:

            failed += 1

            print()
            print(
                f"FAILED: {company[1]}"
            )

            print(error)

        # Small pause to avoid hammering APIs
        time.sleep(1)

    print()
    print("=" * 60)
    print("AGENT 2 COMPLETE")
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
