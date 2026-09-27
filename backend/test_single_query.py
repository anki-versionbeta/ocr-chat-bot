"""Single query test"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from services.multiagent_cypher_service import run_fewshot_cypher_generation

PROCESS_ID = "f96d6d53-8257-4d3c-86b1-279f0e3ad069"

# Test normal extraction that should work
print("="*60)
print("TEST: Normal Row Extraction")
print("="*60)

start = time.time()
result = run_fewshot_cypher_generation(
    user_query="Get all Ges.-Mittel. row values",
    process_id=PROCESS_ID,
    max_iterations=2
)
duration = time.time() - start

print(f"\nRESULT:")
print(f"  Success: {result.get('success')}")
print(f"  Rows: {result.get('result_count')}")
print(f"  Duration: {duration:.1f}s")
print(f"  Error: {result.get('execution_error', 'None')}")

if result.get('results'):
    print(f"  Sample: {result['results'][0]}")
