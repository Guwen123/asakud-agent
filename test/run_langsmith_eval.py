from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from evaluators import score_output
from run_agent_eval import DEFAULT_CASES, cleanup_eval_side_effects, load_cases, model_configuration_error, skip_reason_for


DEFAULT_DATASET_NAME = "asakud-agent-regression"
DEFAULT_EXPERIMENT_PREFIX = "asakud-agent-langsmith"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run asakud-agent evaluations in LangSmith.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="Path to JSONL eval cases.")
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME, help="LangSmith dataset name.")
    parser.add_argument("--experiment-prefix", default=DEFAULT_EXPERIMENT_PREFIX, help="LangSmith experiment prefix.")
    parser.add_argument("--case-id", action="append", default=[], help="Run only selected case id. Repeatable.")
    parser.add_argument("--category", action="append", default=[], help="Run only selected category. Repeatable.")
    parser.add_argument("--include-network", action="store_true", help="Run cases marked requires=['network'].")
    parser.add_argument("--include-side-effects", action="store_true", help="Run cases that may write reminders/memory.")
    parser.add_argument("--no-cleanup", action="store_true", help="Do not clean reminders created by side-effect evals.")
    parser.add_argument("--no-debug", action="store_true", help="Do not request workflow debug payload from the agent.")
    parser.add_argument("--max-concurrency", type=int, default=1, help="LangSmith evaluation concurrency.")
    parser.add_argument("--dry-run", action="store_true", help="Validate cases and LangSmith env without uploading/running.")
    parser.add_argument(
        "--upload-only",
        action="store_true",
        help="Create a timestamped LangSmith dataset from selected cases without running eval.",
    )
    args = parser.parse_args()

    dependency_error = langsmith_dependency_error()
    if dependency_error:
        print(dependency_error)
        return 2

    env_error = langsmith_environment_error()
    if env_error:
        print(env_error)
        return 2

    cases = selected_cases(args)
    if not cases:
        print("No cases selected.")
        return 1

    runnable_cases = [
        case
        for case in cases
        if not skip_reason_for(
            case,
            include_network=args.include_network,
            include_side_effects=args.include_side_effects,
        )
    ]
    skipped = len(cases) - len(runnable_cases)

    if args.dry_run:
        print(f"selected_cases={len(cases)} runnable_cases={len(runnable_cases)} skipped={skipped}")
        for case in cases:
            reason = skip_reason_for(
                case,
                include_network=args.include_network,
                include_side_effects=args.include_side_effects,
            )
            suffix = f" skipped={reason}" if reason else ""
            print(f"{case['id']} [{case.get('category', '')}]{suffix}")
        return 0

    model_error = model_configuration_error()
    if model_error and not args.upload_only:
        print(model_error)
        print("Fill model settings from the dashboard before running LangSmith experiments.")
        return 2

    from langsmith import Client

    client = Client()
    dataset_name = dataset_name_for(args.dataset_name, cases=runnable_cases)
    dataset = create_langsmith_dataset(client, dataset_name=dataset_name, cases=runnable_cases)
    print(f"LangSmith dataset ready: {dataset_name} cases={len(runnable_cases)} skipped={skipped}")

    if args.upload_only:
        print("Upload-only mode completed.")
        return 0

    target = build_target(include_debug=not args.no_debug, cleanup=not args.no_cleanup)
    results = client.evaluate(
        target,
        data=dataset_name,
        evaluators=[contract_assertions_evaluator, response_shape_evaluator, latency_breakdown_evaluator],
        experiment_prefix=args.experiment_prefix,
        max_concurrency=max(int(args.max_concurrency or 1), 1),
    )
    print(results)
    return 0


def selected_cases(args: argparse.Namespace) -> list[dict[str, Any]]:
    cases = load_cases(Path(args.cases))
    case_ids = set(args.case_id or [])
    categories = set(args.category or [])
    result: list[dict[str, Any]] = []
    for case in cases:
        if case_ids and str(case.get("id", "")) not in case_ids:
            continue
        if categories and str(case.get("category", "")) not in categories:
            continue
        result.append(case)
    return result


def build_target(*, include_debug: bool, cleanup: bool):
    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        from agent_loop.loop import run_agent_once_async

        started_at = dt.datetime.now(dt.timezone.utc).isoformat()
        started = time.perf_counter()
        output = asyncio.run(
            run_agent_once_async(
                str(inputs.get("input", "") or ""),
                message_target=inputs.get("message_target"),
                include_debug=include_debug,
            )
        )
        output["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        if cleanup and bool(inputs.get("side_effects", False)):
            cleanup_eval_side_effects(
                {
                    "message_target": inputs.get("message_target"),
                    "side_effects": inputs.get("side_effects"),
                },
                started_at,
            )
        return output

    return target


def contract_assertions_evaluator(
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> dict[str, Any]:
    _ = inputs
    assertions = reference_outputs.get("assertions", {}) if isinstance(reference_outputs, dict) else {}
    failures = score_output(outputs, assertions if isinstance(assertions, dict) else {})
    return {
        "key": "contract_assertions",
        "score": 0 if failures else 1,
        "comment": "\n".join(failures) if failures else "passed",
    }


def response_shape_evaluator(outputs: dict[str, Any]) -> list[dict[str, Any]]:
    message = str(outputs.get("message", "") or "")
    return [
        {
            "key": "has_message",
            "score": 1 if message.strip() else 0,
            "comment": "message is non-empty" if message.strip() else "message is empty",
        },
        {
            "key": "latency_seconds",
            "score": float(outputs.get("elapsed_seconds", 0.0) or 0.0),
        },
    ]


def latency_breakdown_evaluator(outputs: dict[str, Any]) -> list[dict[str, Any]]:
    trace = _performance_trace(outputs)
    if not trace:
        return [
            {
                "key": "performance_trace_present",
                "score": 0,
                "comment": "debug.performance is missing; run without --no-debug and keep WorkflowState.performance.",
            }
        ]

    nodes = _dict_items(trace.get("nodes", []))
    tools = _dict_items(trace.get("tools", []))
    models = _dict_items(trace.get("model_calls", []))
    tokens = trace.get("tokens", {}) if isinstance(trace.get("tokens", {}), dict) else {}
    slowest_node = _slowest_duration_item(nodes, "name")
    slowest_tool = _slowest_duration_item(tools, "name")
    slowest_model = _slowest_duration_item(models, "model_key")

    return [
        {"key": "performance_trace_present", "score": 1, "comment": str(trace.get("trace_id", "") or "")},
        {"key": "trace_total_ms", "score": _number(trace.get("total_duration_ms"))},
        {"key": "node_total_ms", "score": _sum_duration(nodes)},
        {"key": "tool_total_ms", "score": _sum_duration(tools)},
        {"key": "model_total_ms", "score": _sum_duration(models)},
        {"key": "slowest_node_ms", "score": slowest_node["duration_ms"], "comment": slowest_node["label"]},
        {"key": "slowest_tool_ms", "score": slowest_tool["duration_ms"], "comment": slowest_tool["label"]},
        {"key": "slowest_model_ms", "score": slowest_model["duration_ms"], "comment": slowest_model["label"]},
        {"key": "node_count", "score": float(len(nodes))},
        {"key": "tool_count", "score": float(len(tools))},
        {"key": "model_call_count", "score": float(len(models))},
        {"key": "actual_total_tokens", "score": _number(tokens.get("total_tokens"))},
        {"key": "estimated_total_tokens", "score": _number(tokens.get("estimated_total_tokens"))},
    ]


def create_langsmith_dataset(client: Any, *, dataset_name: str, cases: list[dict[str, Any]]) -> Any:
    dataset = client.create_dataset(
        dataset_name=dataset_name,
        description="asakud-agent regression cases synced from test/cases/agent_eval_cases.jsonl",
    )
    examples = [case_to_langsmith_example(case) for case in cases]
    if examples:
        client.create_examples(dataset_id=dataset.id, examples=examples)
    return dataset


def case_to_langsmith_example(case: dict[str, Any]) -> dict[str, Any]:
    inputs = {
        "case_id": str(case.get("id", "") or ""),
        "category": str(case.get("category", "") or ""),
        "input": str(case.get("input", "") or ""),
        "message_target": case.get("message_target"),
        "requires": case.get("requires", []),
        "side_effects": bool(case.get("side_effects", False)),
    }
    outputs = {
        "assertions": case.get("assertions", {}),
        "notes": str(case.get("notes", "") or ""),
    }
    return {
        "inputs": inputs,
        "outputs": outputs,
        "metadata": {
            "case_id": inputs["case_id"],
            "category": inputs["category"],
            "requires": inputs["requires"],
            "side_effects": inputs["side_effects"],
        },
    }


def dataset_name_for(base_name: str, *, cases: list[dict[str, Any]]) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    categories = sorted({str(case.get("category", "") or "uncategorized") for case in cases})
    suffix = "-".join(categories[:3]) if categories else "empty"
    return f"{base_name}-{suffix}-{stamp}"


def _performance_trace(outputs: dict[str, Any]) -> dict[str, Any]:
    debug = outputs.get("debug", {}) if isinstance(outputs.get("debug", {}), dict) else {}
    trace = debug.get("performance", {}) if isinstance(debug.get("performance", {}), dict) else {}
    return trace


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _sum_duration(items: list[dict[str, Any]]) -> float:
    return round(sum(_number(item.get("duration_ms")) for item in items), 3)


def _slowest_duration_item(items: list[dict[str, Any]], label_key: str) -> dict[str, Any]:
    if not items:
        return {"label": "", "duration_ms": 0.0}
    item = max(items, key=lambda candidate: _number(candidate.get("duration_ms")))
    return {
        "label": str(item.get(label_key, "") or item.get("name", "") or ""),
        "duration_ms": _number(item.get("duration_ms")),
    }


def _number(value: Any) -> float:
    try:
        return round(float(value or 0.0), 3)
    except (TypeError, ValueError):
        return 0.0


def langsmith_dependency_error() -> str:
    try:
        import langsmith  # noqa: F401
    except ImportError:
        return "Missing dependency: langsmith. Run `pip install -r requirements.txt` first."
    return ""


def langsmith_environment_error() -> str:
    if not str(os.getenv("LANGSMITH_API_KEY", "") or "").strip():
        return "Missing LANGSMITH_API_KEY. Set it before running LangSmith evaluation."
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
