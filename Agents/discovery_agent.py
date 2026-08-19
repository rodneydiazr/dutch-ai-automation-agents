import os
import json
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
TEST_MODE = True
COMPANY_TARGET = 5


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
# SEARCH DUTCH COMPANIES
# ============================================================

def search_companies():

    print()
    print("=" * 60)
    print("AGENT 1 - SEARCHING FOR DUTCH COMPANIES")
    print("=" * 60)

    queries = [
        "Dutch construction companies Netherlands bouwbedrijf",
        "construction contractors Netherlands bouwbedrijf aannemer",
        "Dutch civil engineering construction companies Netherlands",
        "Dutch commercial construction companies Netherlands",
        "Dutch infrastructure construction companies Netherlands",
    ]
    if TEST_MODE:
        queries = queries[:1]
    all_results = []

    for query in queries:

        print()
        print(f"Searching: {query}")

        try:

            results = tavily.search(
                query=query,
                search_depth="advanced",
                max_results=10
            )

            results_list = results.get(
                "results",
                []
            )

            print(
                f"Found {len(results_list)} results"
            )

            all_results.extend(
                results_list
            )

        except Exception as error:

            print(
                f"Search failed: {error}"
            )

    print()
    print(
        f"Total web results collected: "
        f"{len(all_results)}"
    )

    return all_results


# ============================================================
# CLAUDE DISCOVERY
# ============================================================

def analyze_companies(search_results):

    print()
    print("Sending web research to Claude...")

    research = json.dumps(
        search_results,
        ensure_ascii=False,
        indent=2,
        default=str
    )

    schema = {
        "type": "object",
        "properties": {
            "companies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company_name": {
                            "type": "string"
                        },
                        "website": {
                            "type": ["string", "null"]
                        },
                        "industry": {
                            "type": "string"
                        },
                        "location": {
                            "type": "string"
                        },
                        "employee_estimate": {
                            "type": ["integer", "null"]
                        },
                        "company_description": {
                            "type": "string"
                        },
                        "source_url": {
                            "type": ["string", "null"]
                        }
                    },
                    "required": [
                        "company_name",
                        "website",
                        "industry",
                        "location",
                        "employee_estimate",
                        "company_description",
                        "source_url"
                    ],
                    "additionalProperties": False
                }
            }
        },
        "required": [
            "companies"
        ],
        "additionalProperties": False
    }

    prompt = f"""
You are Agent 1 in an AI automation consulting pipeline.

Your job is to discover exactly {COMPANY_TARGET} legitimate
Dutch construction-related companies that could potentially
become AI automation consulting prospects.

Use ONLY the supplied web research.

Do NOT invent companies.

Do NOT create fictional websites.

Prioritize real companies headquartered or operating in the
Netherlands.

Look for:

- construction companies
- building contractors
- civil engineering companies
- infrastructure contractors
- commercial construction companies
- residential construction companies
- engineering/construction firms

IMPORTANT WEBSITE RULE:

If the research contains a company's official website,
include it.

If the official website cannot be reliably identified,
return null.

Do not put a search-result URL into the website field unless
it is actually the company's official website.

For each company return:

company_name
website
industry
location
employee_estimate
company_description
source_url

employee_estimate may be null when reliable information is
not available.

source_url should be the web source supporting the company.

Return up to {COMPANY_TARGET} UNIQUE companies.

Avoid duplicates.

WEB RESEARCH:

{research}
"""

    response = claude.messages.create(
        model=MODEL,
        max_tokens=12000,
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

    print()
    print(
        "Claude response received."
    )

    try:

        data = json.loads(
            text
        )

    except json.JSONDecodeError as error:

        print()
        print("RAW CLAUDE RESPONSE:")
        print(text)
        print()

        raise RuntimeError(
            f"Claude returned invalid JSON: {error}"
        )

    companies = data.get(
        "companies",
        []
    )

    print(
        f"Claude identified "
        f"{len(companies)} companies."
    )

    return companies


# ============================================================
# SAVE COMPANY
# ============================================================

def save_company(company):

    connection = psycopg2.connect(
        DATABASE_URL
    )

    cursor = connection.cursor()

    try:

        company_name = company[
            "company_name"
        ].strip()

        # ----------------------------------------------------
        # CHECK DUPLICATE
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT id
            FROM companies
            WHERE LOWER(name) = LOWER(%s)
            LIMIT 1
            """,
            (
                company_name,
            )
        )

        existing = cursor.fetchone()

        if existing:

            print(
                f"Already exists: "
                f"{company_name}"
            )

            return False

        # ----------------------------------------------------
        # INSERT
        # ----------------------------------------------------

        cursor.execute(
            """
            INSERT INTO companies
            (
                name,
                website,
                industry,
                location,
                employee_estimate,
                description
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                company_name,
                company.get("website"),
                company.get("industry"),
                company.get("location"),
                company.get("employee_estimate"),
                company.get("company_description"),
            )
        )

        connection.commit()

        print(
            f"Saved: {company_name}"
        )

        return True

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
    print("AGENT 1 - COMPANY DISCOVERY")
    print("=" * 60)
    print()

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    search_results = search_companies()

    if not search_results:

        raise RuntimeError(
            "No web search results were returned."
        )

    # --------------------------------------------------------
    # ANALYZE
    # --------------------------------------------------------

    companies = analyze_companies(
        search_results
    )

    if not companies:

        raise RuntimeError(
            "Claude returned zero companies."
        )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    saved = 0
    duplicates = 0
    failed = 0

    print()
    print("=" * 60)
    print("SAVING COMPANIES TO NEON")
    print("=" * 60)

    for company in companies:

        try:

            result = save_company(
                company
            )

            if result:

                saved += 1

            else:

                duplicates += 1

        except Exception as error:

            failed += 1

            print()
            print(
                f"FAILED: "
                f"{company.get('company_name')}"
            )

            print(
                error
            )

    # --------------------------------------------------------
    # FINAL REPORT
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("AGENT 1 COMPLETE")
    print("=" * 60)

    print(
        f"Companies returned: "
        f"{len(companies)}"
    )

    print(
        f"New companies saved: "
        f"{saved}"
    )

    print(
        f"Duplicates skipped: "
        f"{duplicates}"
    )

    print(
        f"Failed: "
        f"{failed}"
    )

    print()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()