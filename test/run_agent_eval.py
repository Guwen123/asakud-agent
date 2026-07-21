from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from evaluators import score_output


DEFAULT_CASES = ROOT / "test" / "cases" / "agent_eval_cases.jsonl"
DEFAULT_RESULTS_DIR = ROOT / "test" / "results"


@dataclass
class CaseResult:
    case_id: str
    category: str
    skipped: bool
    passed: bool
    elapsed_seconds: float
    output: dict[str, Any]
    failures: list[str]
    error: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local asakud-agent eval cases.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="Path to JSONL eval cases.")
    parser.add_argument("--output", default="", help="Optional output JSONL path.")
    parser.add_argument("--case-id", action="append", default=[], help="Run only selected case id. Repeatable.")
    parser.add_argument("--category", action="append", default=[], help="Run only selected category. Repeatable.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and list cases without calling the agent.")
    parser.add_argument("--include-network", action="store_true", help="Run cases marked requires=['network'].")
    parser.add_argument("--include-side-effects", action="store_true", help="Run cases that may write reminders/memory.")
    parser.add_argument("--no-cleanup", action="store_true", help="Do not clean reminders created by side-effect evals.")
    parser.add_argument("--no-debug", action="store_true", help="Do not request workflow debug payload from the agent.")
    parser.add_argument("--report", default="", help="Optional Markdown report path.")
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    selected = filter_cases(cases, case_ids=set(args.case_id), categories=set(args.category))
    if args.dry_run:
        for case in selected:
            print(f"{case['id']} [{case.get('category', 'uncategorized')}] requires={case.get('requires', [])}")
        print(f"validated_cases={len(selected)}")
        return 0

    model_error = model_configuration_error()
    if model_error:
        print(model_error)
        print("Fill model settings from the dashboard, then rerun this command.")
        return 2

    results = asyncio.run(run_cases(selected, args))
    output_path = Path(args.output) if args.output else default_output_path()
    write_results(output_path, results)
    report_path = Path(args.report) if args.report else output_path.with_suffix(".md")
    write_markdown_report(report_path, results)

    passed = sum(1 for item in results if item.passed and not item.skipped)
    skipped = sum(1 for item in results if item.skipped)
    failed = sum(1 for item in results if not item.passed and not item.skipped)
    print(f"passed={passed} failed={failed} skipped={skipped} results={output_path} report={report_path}")
    return 1 if failed else 0


def load_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            case = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        validate_case(case, path, line_number)
        cases.append(case)
    return cases


def validate_case(case: dict[str, Any], path: Path, line_number: int) -> None:
    for key in ("id", "input", "assertions"):
        if key not in case:
            raise ValueError(f"{path}:{line_number}: missing required key: {key}")
    if not isinstance(case["assertions"], dict):
        raise ValueError(f"{path}:{line_number}: assertions must be an object")


def filter_cases(
    cases: list[dict[str, Any]],
    *,
    case_ids: set[str],
    categories: set[str],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for case in cases:
        if case_ids and str(case.get("id")) not in case_ids:
            continue
        if categories and str(case.get("category", "")) not in categories:
            continue
        selected.append(case)
    return selected


def model_configuration_error() -> str:
    from agent_loop.config_loader import load_config

    config = load_config()
    for key in ("main_model", "route_model", "multimodal_model"):
        model = config.get(key)
        if not isinstance(model, dict):
            return f"Model configuration is missing: {key}"
        missing = [
            field
            for field in ("name", "base_url", "api_key")
            if not str(model.get(field, "") or "").strip()
        ]
        if missing:
            return f"Model configuration is incomplete: {key}.{', '.join(missing)}"
    return ""


async def run_cases(cases: list[dict[str, Any]], args: argparse.Namespace) -> list[CaseResult]:
    from agent_loop.loop import run_agent_once_async

    results: list[CaseResult] = []
    for case in cases:
        skip_reason = skip_reason_for(case, include_network=args.include_network, include_side_effects=args.include_side_effects)
        if skip_reason:
            results.append(
                CaseResult(
                    case_id=str(case["id"]),
                    category=str(case.get("category", "")),
                    skipped=True,
                    passed=True,
                    elapsed_seconds=0.0,
                    output={},
                    failures=[],
                    error=skip_reason,
                )
            )
            continue

        started_at = dt.datetime.now(dt.timezone.utc).isoformat()
        start = time.perf_counter()
        try:
            output = await run_agent_once_async(
                str(case["input"]),
                message_target=case.get("message_target"),
                include_debug=not args.no_debug,
            )
            elapsed = time.perf_counter() - start
            failures = score_output(output, case.get("assertions", {}))
            results.append(
                CaseResult(
                    case_id=str(case["id"]),
                    category=str(case.get("category", "")),
                    skipped=False,
                    passed=not failures,
                    elapsed_seconds=elapsed,
                    output=output,
                    failures=failures,
                )
            )
        except Exception as exc:
            elapsed = time.perf_counter() - start
            results.append(
                CaseResult(
                    case_id=str(case["id"]),
                    category=str(case.get("category", "")),
                    skipped=False,
                    passed=False,
                    elapsed_seconds=elapsed,
                    output={},
                    failures=[],
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
        finally:
            if case.get("side_effects") and not args.no_cleanup:
                cleanup_eval_side_effects(case, started_at)

    return results


def skip_reason_for(case: dict[str, Any], *, include_network: bool, include_side_effects: bool) -> str:
    requires = {str(item) for item in case.get("requires", [])}
    if "network" in requires and not include_network:
        return "skipped: requires network; pass --include-network"
    if ("side_effects" in requires or case.get("side_effects")) and not include_side_effects:
        return "skipped: requires side effects; pass --include-side-effects"
    return ""


def cleanup_eval_side_effects(case: dict[str, Any], started_at: str) -> None:
    target = case.get("message_target") if isinstance(case.get("message_target"), dict) else {}
    if not target:
        return
    database_path = ROOT / "db" / "session_memory.db"
    if not database_path.exists():
        return
    fragments: list[str] = []
    if target.get("message_type") == "private" and target.get("user_id") is not None:
        fragments.append(f'"user_id": {int(target["user_id"])}')
    if target.get("message_type") == "group" and target.get("group_id") is not None:
        fragments.append(f'"group_id": {int(target["group_id"])}')
    if not fragments:
        return

    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            "SELECT id, target_json FROM reminders WHERE created_at >= ?",
            (started_at,),
        ).fetchall()
        reminder_ids = [
            row[0]
            for row in rows
            if any(fragment in str(row[1] or "") for fragment in fragments)
        ]
        for reminder_id in reminder_ids:
            conn.execute("DELETE FROM reminder_runs WHERE reminder_id = ?", (reminder_id,))
            conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        conn.commit()


def default_output_path() -> Path:
    DEFAULT_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_RESULTS_DIR / f"agent_eval_{timestamp}.jsonl"


def write_results(path: Path, results: list[CaseResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in results:
            handle.write(
                json.dumps(
                    {
                        "case_id": item.case_id,
                        "category": item.category,
                        "skipped": item.skipped,
                        "passed": item.passed,
                        "elapsed_seconds": round(item.elapsed_seconds, 3),
                        "output": item.output,
                        "failures": item.failures,
                        "error": item.error,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def write_markdown_report(path: Path, results: list[CaseResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for item in results if item.passed and not item.skipped)
    skipped = sum(1 for item in results if item.skipped)
    failed = sum(1 for item in results if not item.passed and not item.skipped)
    lines = [
        "# asakud-agent Evaluation Report",
        "",
        f"- Passed: {passed}",
        f"- Failed: {failed}",
        f"- Skipped: {skipped}",
        "",
        "| Case | Category | Status | Seconds | Trace ms | Tool ms | Model ms | Notes |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in results:
        status = "skipped" if item.skipped else ("passed" if item.passed else "failed")
        notes = item.error or "; ".join(item.failures) or "-"
        perf = _performance_summary(item.output)
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(item.case_id),
                    _escape_table(item.category),
                    status,
                    f"{item.elapsed_seconds:.3f}",
                    f"{perf['trace_total_ms']:.1f}",
                    f"{perf['tool_total_ms']:.1f}",
                    f"{perf['model_total_ms']:.1f}",
                    _escape_table(notes),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _escape_table(value: str) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _performance_summary(output: dict[str, Any]) -> dict[str, float]:
    debug = output.get("debug", {}) if isinstance(output.get("debug", {}), dict) else {}
    trace = debug.get("performance", {}) if isinstance(debug.get("performance", {}), dict) else {}
    tools = _dict_items(trace.get("tools", []))
    models = _dict_items(trace.get("model_calls", []))
    return {
        "trace_total_ms": _safe_float(trace.get("total_duration_ms")),
        "tool_total_ms": sum(_safe_float(item.get("duration_ms")) for item in tools),
        "model_total_ms": sum(_safe_float(item.get("duration_ms")) for item in models),
    }


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
