#!/usr/bin/env python3
"""六大师多顾问系统的最小可执行脚手架。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
RUNTIME_PATH = ROOT / "runtime" / "advisors.json"
PROMPTS_DIR = ROOT / "prompts"
TEMPLATES_DIR = ROOT / "templates"
RUNS_DIR = ROOT / "runs"

REQUEST_REQUIRED_KEYS = [
    "problem_statement",
    "decision_type",
    "time_horizon",
    "background",
    "success_definition",
    "constraints",
    "known_facts",
    "unknowns",
    "selected_advisors",
    "output_priority",
]

ADVISOR_OUTPUT_REQUIRED_KEYS = [
    "advisor_id",
    "advisor_name",
    "problem_reframe",
    "core_judgment",
    "decision_mode",
    "recommended_actions",
    "what_to_cut",
    "non_negotiables",
    "supporting_logic",
    "key_risks",
    "assumptions",
    "open_questions",
    "success_metrics",
    "confidence",
    "limits",
]


@dataclass
class Advisor:
    advisor_id: str
    name: str
    skill: str
    role: str
    domains: list[str]
    ask_first: list[str]
    blind_spots: list[str]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_advisors() -> dict[str, Advisor]:
    payload = read_json(RUNTIME_PATH)
    advisors: dict[str, Advisor] = {}
    for item in payload["advisors"]:
        advisor = Advisor(
            advisor_id=item["id"],
            name=item["name"],
            skill=item["skill"],
            role=item["role"],
            domains=item["domains"],
            ask_first=item["ask_first"],
            blind_spots=item["blind_spots"],
        )
        advisors[advisor.advisor_id] = advisor
    return advisors


def validate_request(payload: dict[str, Any]) -> None:
    missing = [key for key in REQUEST_REQUIRED_KEYS if key not in payload]
    if missing:
        raise ValueError(f"请求文件缺少字段: {', '.join(missing)}")


def load_request(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    validate_request(payload)
    return payload


def select_advisors(
    request_payload: dict[str, Any],
    advisors: dict[str, Advisor],
) -> list[str]:
    requested = request_payload.get("selected_advisors", [])
    if requested:
        invalid = [advisor_id for advisor_id in requested if advisor_id not in advisors]
        if invalid:
            raise ValueError(f"存在未知顾问: {', '.join(invalid)}")
        return requested

    decision_types = set(request_payload.get("decision_type", []))
    if decision_types >= {"strategy", "product", "brand", "organization", "engineering"}:
        return list(advisors.keys())

    selected: list[str] = []
    for advisor_id, advisor in advisors.items():
        if decision_types.intersection(advisor.domains):
            selected.append(advisor_id)

    if not selected:
        selected = ["munger", "drucker", "jobs"]
    return selected


def normalize_request(
    request_payload: dict[str, Any],
    advisors: dict[str, Advisor],
) -> dict[str, Any]:
    selected_ids = select_advisors(request_payload, advisors)
    reason: list[str] = []
    for advisor_id in selected_ids:
        advisor = advisors[advisor_id]
        reason.append(f"{advisor.name} 负责 {advisor.role}")

    normalized = dict(request_payload)
    normalized["selected_advisors"] = selected_ids
    normalized["selection_reason"] = reason
    normalized["prepared_at"] = datetime.now().isoformat(timespec="seconds")
    return normalized


def ensure_run_dir(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "advisor-prompts").mkdir(exist_ok=True)
    (run_dir / "advisor-outputs").mkdir(exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)


def render_advisor_prompt(
    advisor: Advisor,
    request_payload: dict[str, Any],
) -> str:
    return f"""# 顾问任务包

## 顾问信息

- 顾问：{advisor.name}
- 角色：{advisor.role}
- 绑定 skill：`{advisor.skill}`

## 顾问默认追问

{render_bullets(advisor.ask_first)}

## 顾问盲区提醒

{render_bullets(advisor.blind_spots)}

## 统一问题包

```json
{json.dumps(request_payload, ensure_ascii=False, indent=2)}
```

## 执行要求

1. 只从 {advisor.name} 的镜片出发分析问题。
2. 必须按 `templates/advisor-output-schema.md` 的结构输出 JSON。
3. 不要为了和其他顾问一致而压平自己的判断。
4. 如有边界、假设、风险，必须明确写出。
"""


def render_bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def prepare_run(request_path: Path, run_dir: Path) -> None:
    advisors = load_advisors()
    request_payload = load_request(request_path)
    normalized = normalize_request(request_payload, advisors)

    ensure_run_dir(run_dir)
    write_json(run_dir / "request.normalized.json", normalized)

    for advisor_id in normalized["selected_advisors"]:
        advisor = advisors[advisor_id]
        prompt_path = run_dir / "advisor-prompts" / f"{advisor_id}.md"
        prompt_path.write_text(
            render_advisor_prompt(advisor, normalized),
            encoding="utf-8",
        )
        output_placeholder = {
            "advisor_id": advisor.advisor_id,
            "advisor_name": advisor.name,
            "problem_reframe": "",
            "core_judgment": "",
            "decision_mode": "",
            "recommended_actions": [],
            "what_to_cut": [],
            "non_negotiables": [],
            "supporting_logic": [],
            "key_risks": [],
            "assumptions": [],
            "open_questions": [],
            "success_metrics": [],
            "confidence": 0.0,
            "limits": [],
        }
        write_json(run_dir / "advisor-outputs" / f"{advisor_id}.json", output_placeholder)

    summary = {
        "run_dir": str(run_dir),
        "selected_advisors": normalized["selected_advisors"],
        "advisor_prompt_dir": str(run_dir / "advisor-prompts"),
        "advisor_output_dir": str(run_dir / "advisor-outputs"),
    }
    write_json(run_dir / "artifacts" / "run-summary.json", summary)


def validate_advisor_output(payload: dict[str, Any]) -> list[str]:
    missing = [key for key in ADVISOR_OUTPUT_REQUIRED_KEYS if key not in payload]
    problems = list(missing)
    if "confidence" in payload and not isinstance(payload["confidence"], (int, float)):
        problems.append("confidence 必须是数字")
    return problems


def collect_completed_outputs(run_dir: Path) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for path in sorted((run_dir / "advisor-outputs").glob("*.json")):
        payload = read_json(path)
        problems = validate_advisor_output(payload)
        if problems:
            raise ValueError(f"{path.name} 字段不完整: {', '.join(problems)}")
        if payload["core_judgment"]:
            outputs.append(payload)
    return outputs


def render_arbiter_prompt(
    request_payload: dict[str, Any],
    advisor_outputs: list[dict[str, Any]],
) -> str:
    return f"""# 仲裁任务包

## 统一问题包

```json
{json.dumps(request_payload, ensure_ascii=False, indent=2)}
```

## 顾问输出

```json
{json.dumps(advisor_outputs, ensure_ascii=False, indent=2)}
```

## 仲裁要求

1. 提取真正的顾问共识。
2. 保留关键分歧，不要平均意见。
3. 明确主建议、备选建议和不建议做的事。
4. 最终输出请遵循 `templates/final-report-template.md`。
"""


def build_arbiter(run_dir: Path) -> None:
    request_payload = read_json(run_dir / "request.normalized.json")
    outputs = collect_completed_outputs(run_dir)
    if not outputs:
        raise ValueError("当前没有任何已完成的顾问输出，无法生成仲裁输入。")

    write_json(run_dir / "artifacts" / "arbiter-input.json", {
        "request": request_payload,
        "advisor_outputs": outputs,
    })
    (run_dir / "artifacts" / "arbiter-prompt.md").write_text(
        render_arbiter_prompt(request_payload, outputs),
        encoding="utf-8",
    )


def run_status(run_dir: Path) -> dict[str, Any]:
    request_payload = read_json(run_dir / "request.normalized.json")
    selected = request_payload["selected_advisors"]
    completed: list[str] = []
    pending: list[str] = []

    for advisor_id in selected:
        payload = read_json(run_dir / "advisor-outputs" / f"{advisor_id}.json")
        if payload.get("core_judgment"):
            completed.append(advisor_id)
        else:
            pending.append(advisor_id)

    return {
        "run_dir": str(run_dir),
        "selected_advisors": selected,
        "completed": completed,
        "pending": pending,
    }


def default_run_dir(name: str | None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = name or "run"
    return RUNS_DIR / f"{stamp}-{suffix}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="六大师多顾问系统 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-request", help="生成请求模板")
    init_parser.add_argument("--output", type=Path, required=True, help="输出 JSON 文件路径")

    prepare_parser = subparsers.add_parser("prepare-run", help="生成顾问运行包")
    prepare_parser.add_argument("--input", type=Path, required=True, help="请求 JSON 路径")
    prepare_parser.add_argument("--run-dir", type=Path, help="运行目录")
    prepare_parser.add_argument("--name", help="运行名称，仅在未传 run-dir 时使用")

    arbiter_parser = subparsers.add_parser("build-arbiter", help="基于顾问输出生成仲裁输入")
    arbiter_parser.add_argument("--run-dir", type=Path, required=True, help="运行目录")

    status_parser = subparsers.add_parser("status", help="查看运行状态")
    status_parser.add_argument("--run-dir", type=Path, required=True, help="运行目录")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.command == "init-request":
            sample = read_json(ROOT / "examples" / "request.sample.json")
            write_json(args.output, sample)
            print(f"已生成请求模板：{args.output}")
            return 0

        if args.command == "prepare-run":
            run_dir = args.run_dir or default_run_dir(args.name)
            prepare_run(args.input, run_dir)
            print(f"已生成运行包：{run_dir}")
            return 0

        if args.command == "build-arbiter":
            build_arbiter(args.run_dir)
            print(f"已生成仲裁输入：{args.run_dir / 'artifacts' / 'arbiter-prompt.md'}")
            return 0

        if args.command == "status":
            payload = run_status(args.run_dir)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:  # noqa: BLE001
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
