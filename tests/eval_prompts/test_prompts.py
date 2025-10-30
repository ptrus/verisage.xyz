#!/usr/bin/env python3
"""Test script for running prompt test cases against the Verisage API.

This script:
1. Reads test cases from test_cases.json
2. Submits each query to the API
3. Polls for results
4. Saves detailed responses
5. Generates a summary report
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import httpx


class PromptTester:
    """Test runner for Verisage prompts."""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 120):
        """Initialize the tester.

        Args:
            base_url: Base URL of the Verisage API
            timeout: Maximum time to wait for each query (seconds)
        """
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.Client(timeout=30.0)
        self.results = []

    def load_test_cases(self, filepath: str = "test_cases.json") -> list[dict]:
        """Load test cases from JSON file.

        Args:
            filepath: Path to test cases JSON file

        Returns:
            List of test case dictionaries
        """
        with open(filepath) as f:
            data = json.load(f)
        return data["test_cases"]

    def submit_query(self, query: str) -> dict | None:
        """Submit a query to the API.

        Args:
            query: The query string

        Returns:
            Response dict with job_id, or None on error
        """
        try:
            response = self.client.post(f"{self.base_url}/api/v1/query", json={"query": query})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"  ❌ Error submitting query: {e}")
            return None

    def poll_result(self, job_id: str, poll_interval: float = 2.0) -> dict | None:
        """Poll for query result.

        Args:
            job_id: Job identifier
            poll_interval: Seconds between polls

        Returns:
            Result dict or None on timeout/error
        """
        start_time = time.time()

        while time.time() - start_time < self.timeout:
            try:
                response = self.client.get(f"{self.base_url}/api/v1/query/{job_id}")
                response.raise_for_status()
                data = response.json()

                status = data.get("status")

                if status == "completed":
                    return data
                elif status == "failed":
                    print(f"  ❌ Job failed: {data.get('error', 'Unknown error')}")
                    return data
                elif status in ["pending", "processing"]:
                    print(f"  ⏳ Status: {status}... (elapsed: {int(time.time() - start_time)}s)")
                    time.sleep(poll_interval)
                else:
                    print(f"  ⚠️  Unknown status: {status}")
                    time.sleep(poll_interval)

            except Exception as e:
                print(f"  ❌ Error polling result: {e}")
                return None

        print(f"  ⏱️  Timeout after {self.timeout}s")
        return None

    def run_test_case(self, test_case: dict) -> dict:
        """Run a single test case.

        Args:
            test_case: Test case dictionary

        Returns:
            Result dictionary with test outcome
        """
        test_id = test_case["id"]
        query = test_case["query"]
        expected_decision = test_case["expected_decision"]
        min_confidence = test_case.get("min_confidence", 0.5)

        print(f"\n{'=' * 80}")
        print(f"Test: {test_id}")
        print(f"Category: {test_case['category']}")
        print(f"Query: {query}")
        print(f"Expected: {expected_decision} (min confidence: {min_confidence})")
        print(f"{'=' * 80}")

        start_time = time.time()

        # Submit query
        print("📤 Submitting query...")
        submit_response = self.submit_query(query)
        if not submit_response:
            return {
                "test_id": test_id,
                "status": "error",
                "error": "Failed to submit query",
                "query": query,
                "expected_decision": expected_decision,
            }

        job_id = submit_response.get("job_id")
        print(f"✓ Job created: {job_id}")

        # Poll for result
        print("⏳ Waiting for result...")
        result = self.poll_result(job_id)

        elapsed_time = time.time() - start_time

        if not result:
            return {
                "test_id": test_id,
                "status": "timeout",
                "error": f"Timeout after {self.timeout}s",
                "query": query,
                "expected_decision": expected_decision,
                "elapsed_time": elapsed_time,
            }

        # Analyze result
        oracle_result = result.get("result")
        if not oracle_result:
            return {
                "test_id": test_id,
                "status": "failed",
                "error": result.get("error", "No result returned"),
                "query": query,
                "expected_decision": expected_decision,
                "elapsed_time": elapsed_time,
                "full_response": result,
            }

        actual_decision = oracle_result.get("final_decision")
        actual_confidence = oracle_result.get("final_confidence")

        # Determine if test passed
        decision_match = actual_decision == expected_decision
        confidence_ok = actual_confidence >= min_confidence

        passed = decision_match and confidence_ok

        status_emoji = "✅" if passed else "❌"
        print(f"\n{status_emoji} Result: {actual_decision} (confidence: {actual_confidence:.2f})")
        print(f"   Decision Match: {'✓' if decision_match else '✗'}")
        print(f"   Confidence OK: {'✓' if confidence_ok else '✗'}")
        print(f"   Elapsed Time: {elapsed_time:.1f}s")

        return {
            "test_id": test_id,
            "category": test_case["category"],
            "query": query,
            "expected_decision": expected_decision,
            "actual_decision": actual_decision,
            "expected_min_confidence": min_confidence,
            "actual_confidence": actual_confidence,
            "decision_match": decision_match,
            "confidence_ok": confidence_ok,
            "passed": passed,
            "elapsed_time": elapsed_time,
            "tags": test_case.get("tags", []),
            "notes": test_case.get("notes", ""),
            "full_response": oracle_result,
        }

    def run_all_tests(self, test_cases: list[dict]) -> list[dict]:
        """Run all test cases.

        Args:
            test_cases: List of test case dicts

        Returns:
            List of result dicts
        """
        results = []

        for i, test_case in enumerate(test_cases, 1):
            print(f"\n\n{'#' * 80}")
            print(f"# Test {i}/{len(test_cases)}")
            print(f"{'#' * 80}")

            result = self.run_test_case(test_case)
            results.append(result)

            # Small delay between tests
            if i < len(test_cases):
                time.sleep(1)

        return results

    def generate_report(self, results: list[dict]) -> dict:
        """Generate summary report from results.

        Args:
            results: List of test result dicts

        Returns:
            Report dictionary
        """
        total = len(results)
        passed = sum(1 for r in results if r.get("passed", False))
        failed = total - passed

        decision_matches = sum(1 for r in results if r.get("decision_match", False))
        confidence_passes = sum(1 for r in results if r.get("confidence_ok", False))

        # Category breakdown
        categories = {}
        for result in results:
            cat = result.get("category", "unknown")
            if cat not in categories:
                categories[cat] = {"total": 0, "passed": 0}
            categories[cat]["total"] += 1
            if result.get("passed", False):
                categories[cat]["passed"] += 1

        # Average metrics
        avg_time = sum(r.get("elapsed_time", 0) for r in results) / total if total > 0 else 0
        avg_confidence = (
            sum(r.get("actual_confidence", 0) for r in results if r.get("actual_confidence"))
            / sum(1 for r in results if r.get("actual_confidence"))
            if any(r.get("actual_confidence") for r in results)
            else 0
        )

        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": (passed / total * 100) if total > 0 else 0,
                "decision_matches": decision_matches,
                "confidence_passes": confidence_passes,
            },
            "metrics": {
                "avg_elapsed_time": avg_time,
                "avg_confidence": avg_confidence,
            },
            "categories": categories,
            "results": results,
        }

    def save_report(self, report: dict, output_dir: str = "test_results"):
        """Save report to files.

        Args:
            report: Report dictionary
            output_dir: Directory to save results
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save full JSON report
        json_path = output_path / f"report_{timestamp}.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n💾 Saved JSON report: {json_path}")

        # Save human-readable summary
        summary_path = output_path / f"summary_{timestamp}.txt"
        with open(summary_path, "w") as f:
            self._write_summary(f, report)
        print(f"💾 Saved summary: {summary_path}")

    def _write_summary(self, f, report: dict):
        """Write human-readable summary to file."""
        f.write("=" * 80 + "\n")
        f.write("VERISAGE PROMPT TEST REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(f"Timestamp: {report['timestamp']}\n")
        f.write("\n")

        summary = report["summary"]
        f.write("SUMMARY\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total Tests:      {summary['total_tests']}\n")
        f.write(f"Passed:           {summary['passed']} ✅\n")
        f.write(f"Failed:           {summary['failed']} ❌\n")
        f.write(f"Pass Rate:        {summary['pass_rate']:.1f}%\n")
        f.write(f"Decision Matches: {summary['decision_matches']}/{summary['total_tests']}\n")
        f.write(f"Confidence Passes: {summary['confidence_passes']}/{summary['total_tests']}\n")
        f.write("\n")

        metrics = report["metrics"]
        f.write("METRICS\n")
        f.write("-" * 80 + "\n")
        f.write(f"Avg Elapsed Time: {metrics['avg_elapsed_time']:.1f}s\n")
        f.write(f"Avg Confidence:   {metrics['avg_confidence']:.2f}\n")
        f.write("\n")

        f.write("CATEGORY BREAKDOWN\n")
        f.write("-" * 80 + "\n")
        for cat, stats in report["categories"].items():
            pass_rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            f.write(f"{cat:20s}: {stats['passed']}/{stats['total']} ({pass_rate:.0f}%)\n")
        f.write("\n")

        f.write("DETAILED RESULTS\n")
        f.write("-" * 80 + "\n")
        for result in report["results"]:
            status = "✅ PASS" if result.get("passed") else "❌ FAIL"
            f.write(f"\n{status} - {result['test_id']}\n")
            f.write(f"  Query: {result['query']}\n")
            f.write(
                f"  Expected: {result['expected_decision']} | "
                f"Actual: {result.get('actual_decision', 'N/A')}\n"
            )
            f.write(
                f"  Confidence: {result.get('actual_confidence', 0):.2f} "
                f"(min: {result['expected_min_confidence']:.2f})\n"
            )
            f.write(f"  Time: {result.get('elapsed_time', 0):.1f}s\n")
            if not result.get("passed"):
                if not result.get("decision_match"):
                    f.write("  ⚠️  Decision mismatch\n")
                if not result.get("confidence_ok"):
                    f.write("  ⚠️  Confidence too low\n")

    def print_summary(self, report: dict):
        """Print summary to console."""
        print("\n\n")
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)

        summary = report["summary"]
        print(f"\nTotal Tests:      {summary['total_tests']}")
        print(f"Passed:           {summary['passed']} ✅")
        print(f"Failed:           {summary['failed']} ❌")
        print(f"Pass Rate:        {summary['pass_rate']:.1f}%")
        print(f"Decision Matches: {summary['decision_matches']}/{summary['total_tests']}")
        print(f"Confidence Passes: {summary['confidence_passes']}/{summary['total_tests']}")

        metrics = report["metrics"]
        print(f"\nAvg Elapsed Time: {metrics['avg_elapsed_time']:.1f}s")
        print(f"Avg Confidence:   {metrics['avg_confidence']:.2f}")

        print("\nCategory Breakdown:")
        for cat, stats in report["categories"].items():
            pass_rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            print(f"  {cat:20s}: {stats['passed']}/{stats['total']} ({pass_rate:.0f}%)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run Verisage prompt tests")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of Verisage API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout per query in seconds (default: 120)",
    )
    parser.add_argument(
        "--test-cases",
        default="test_cases.json",
        help="Path to test cases JSON file (default: test_cases.json)",
    )
    parser.add_argument(
        "--output-dir",
        default="test_results",
        help="Directory to save results (default: test_results)",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("VERISAGE PROMPT TESTER")
    print("=" * 80)
    print(f"API URL: {args.url}")
    print(f"Timeout: {args.timeout}s")
    print(f"Test Cases: {args.test_cases}")
    print(f"Output Dir: {args.output_dir}")

    # Initialize tester
    tester = PromptTester(base_url=args.url, timeout=args.timeout)

    # Load test cases
    print(f"\n📋 Loading test cases from {args.test_cases}...")
    try:
        test_cases = tester.load_test_cases(args.test_cases)
        print(f"✓ Loaded {len(test_cases)} test cases")
    except Exception as e:
        print(f"❌ Error loading test cases: {e}")
        return 1

    # Check API health
    print("\n🏥 Checking API health...")
    try:
        response = tester.client.get(f"{args.url}/health")
        response.raise_for_status()
        print("✓ API is healthy")
    except Exception as e:
        print(f"❌ API health check failed: {e}")
        print("Make sure the server is running: uv run python -m src.main")
        return 1

    # Run tests
    print("\n🚀 Starting test run...")
    results = tester.run_all_tests(test_cases)

    # Generate report
    print("\n📊 Generating report...")
    report = tester.generate_report(results)

    # Save report
    tester.save_report(report, args.output_dir)

    # Print summary
    tester.print_summary(report)

    # Exit with appropriate code
    if report["summary"]["failed"] > 0:
        print("\n❌ Some tests failed")
        return 1
    else:
        print("\n✅ All tests passed!")
        return 0


if __name__ == "__main__":
    exit(main())
