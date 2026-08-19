import sys
import time
from datetime import datetime

from Agents.discovery_agent import main as discovery_main
from Agents.research_agent import main as research_main
from Agents.validation_agent import main as validation_main
from Agents.solution_agent import main as solution_main
from Agents.final_ranking_agent import main as ranking_main


def run_stage(name, function):
    print("\n" + "=" * 70)
    print(f"STARTING: {name}")
    print("=" * 70)

    start_time = time.time()

    try:
        result = function()

        elapsed = time.time() - start_time

        print("\n" + "-" * 70)
        print(f"COMPLETED: {name}")
        print(f"Time: {elapsed:.2f} seconds")
        print("-" * 70)

        return result

    except Exception as error:
        elapsed = time.time() - start_time

        print("\n" + "!" * 70)
        print(f"FAILED: {name}")
        print(f"Time: {elapsed:.2f} seconds")
        print(f"Error: {error}")
        print("!" * 70)

        raise


def main():
    print("\n" + "#" * 70)
    print("AI AUTOMATION OPPORTUNITY DISCOVERY SYSTEM")
    print("#" * 70)
    print(f"Pipeline started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    pipeline_start = time.time()

    try:
        run_stage("1. COMPANY DISCOVERY", discovery_main)

        run_stage("2. COMPANY RESEARCH", research_main)

        run_stage("3. OPPORTUNITY VALIDATION", validation_main)

        run_stage("4. SOLUTION IDENTIFICATION", solution_main)

        run_stage("5. FINAL RANKING", ranking_main)

        total_time = time.time() - pipeline_start

        print("\n" + "#" * 70)
        print("PIPELINE COMPLETED SUCCESSFULLY")
        print("#" * 70)
        print(f"Total execution time: {total_time:.2f} seconds")
        print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("#" * 70)

    except Exception:
        total_time = time.time() - pipeline_start

        print("\n" + "#" * 70)
        print("PIPELINE FAILED")
        print("#" * 70)
        print(f"Elapsed time: {total_time:.2f} seconds")
        print("#" * 70)

        sys.exit(1)


if __name__ == "__main__":
    main()
    