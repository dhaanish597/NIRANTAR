"""Phase 6 TDD tests: Quantitative Benchmarks, Telemetry Usage Report, Code Quality Audit & DECISIONS.md."""
from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


class TestPhase6BenchmarksAndAudit(unittest.TestCase):
    def test_01_run_hackfront_benchmarks_generates_evaluation_and_usage_reports(self) -> None:
        from scripts.run_hackfront_benchmarks import run_all_benchmarks_and_write_reports

        summary = run_all_benchmarks_and_write_reports(REPO_ROOT)
        self.assertEqual(summary["status"], "PASS")
        self.assertGreaterEqual(summary["total_model_calls"], 4)
        self.assertGreaterEqual(summary["total_tool_calls"], 8)
        self.assertEqual(summary["citation_hallucination_rate"], 0.0)

        eval_path = REPO_ROOT / "evaluation" / "evaluation_report.md"
        usage_path = REPO_ROOT / "evaluation" / "usage_report.md"
        self.assertTrue(eval_path.exists())
        self.assertTrue(usage_path.exists())
        eval_text = eval_path.read_text(encoding="utf-8")
        usage_text = usage_path.read_text(encoding="utf-8")
        self.assertIn("Cascade Blast-Radius Recall", eval_text)
        self.assertIn("Choke-Point Precision", eval_text)
        self.assertIn("total_model_calls", usage_text)

    def test_02_code_quality_audit_enforces_line_caps_and_zero_hardcoding(self) -> None:
        from scripts.audit_code_quality import run_strict_code_quality_audit

        report = run_strict_code_quality_audit(REPO_ROOT)
        self.assertTrue(
            report["passed"],
            msg=f"Code quality audit failed with violations: {report['violations']}",
        )
        self.assertEqual(len(report["violations"]), 0)

    def test_03_decisions_md_exists_and_documents_five_architectural_tradeoffs(self) -> None:
        decisions_path = REPO_ROOT / "DECISIONS.md"
        self.assertTrue(decisions_path.exists())
        content = decisions_path.read_text(encoding="utf-8")
        self.assertIn("AuraDB", content)
        self.assertIn("HybridCypherRetriever", content)
        self.assertIn("Saaras v4", content)
        self.assertIn("Bulbul v4-flash", content)
        self.assertIn("CoE-AWRDS", content)


if __name__ == "__main__":
    unittest.main()
