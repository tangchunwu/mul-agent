#!/usr/bin/env python3
"""六大师多顾问系统的最小可执行脚手架。"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib import error, request


ROOT = Path(__file__).resolve().parent
RUNTIME_PATH = ROOT / "runtime" / "advisors.json"
PROMPTS_DIR = ROOT / "prompts"
RUNS_DIR = ROOT / "runs"
SKILLS_DIR = ROOT.parent / "skills"

DEFAULT_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEFAULT_ADVISOR_MODEL = os.getenv("MUL_AGENT_ADVISOR_MODEL", "gpt-5.1")
DEFAULT_ARBITER_MODEL = os.getenv("MUL_AGENT_ARBITER_MODEL", "gpt-5.1")
DEFAULT_REASONING_EFFORT = os.getenv("MUL_AGENT_REASONING_EFFORT", "medium")
DEFAULT_TIMEOUT = int(os.getenv("MUL_AGENT_TIMEOUT", "180"))
DEFAULT_MAX_WORKERS = int(os.getenv("MUL_AGENT_MAX_WORKERS", "6"))

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


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def write_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


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
    normalized["prepared_at"] = now_iso()
    return normalized


def ensure_run_dir(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "advisor-prompts").mkdir(exist_ok=True)
    (run_dir / "advisor-outputs").mkdir(exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    (run_dir / "api-responses").mkdir(exist_ok=True)


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


def placeholder_output(advisor: Advisor) -> dict[str, Any]:
    return {
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


def prepare_run(request_path: Path, run_dir: Path) -> None:
    advisors = load_advisors()
    request_payload = load_request(request_path)
    normalized = normalize_request(request_payload, advisors)

    ensure_run_dir(run_dir)
    write_json(run_dir / "request.normalized.json", normalized)

    for advisor_id in normalized["selected_advisors"]:
        advisor = advisors[advisor_id]
        prompt_path = run_dir / "advisor-prompts" / f"{advisor_id}.md"
        write_text(prompt_path, render_advisor_prompt(advisor, normalized))
        write_json(run_dir / "advisor-outputs" / f"{advisor_id}.json", placeholder_output(advisor))

    summary = {
        "run_dir": str(run_dir),
        "selected_advisors": normalized["selected_advisors"],
        "advisor_prompt_dir": str(run_dir / "advisor-prompts"),
        "advisor_output_dir": str(run_dir / "advisor-outputs"),
        "prepared_at": now_iso(),
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


def build_arbiter_inputs(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    request_payload = read_json(run_dir / "request.normalized.json")
    outputs = collect_completed_outputs(run_dir)
    if not outputs:
        raise ValueError("当前没有任何已完成的顾问输出，无法生成仲裁输入。")

    write_json(
        run_dir / "artifacts" / "arbiter-input.json",
        {
            "request": request_payload,
            "advisor_outputs": outputs,
        },
    )
    write_text(
        run_dir / "artifacts" / "arbiter-prompt.md",
        render_arbiter_prompt(request_payload, outputs),
    )
    return request_payload, outputs


def build_arbiter(run_dir: Path) -> None:
    build_arbiter_inputs(run_dir)


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
        "arbiter_completed": (run_dir / "artifacts" / "final-report.json").exists(),
    }


def default_run_dir(name: str | None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = name or "run"
    return RUNS_DIR / f"{stamp}-{suffix}"


def require_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("缺少 OPENAI_API_KEY 环境变量，无法调用模型。")
    return api_key


def load_skill_text(skill_name: str) -> str:
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"缺少 skill 文件: {skill_path}")
    return read_text(skill_path)


def load_prompt_template(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"缺少 prompt 模板: {path}")
    return read_text(path)


def string_array_schema(description: str, max_items: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "array",
        "description": description,
        "items": {"type": "string"},
    }
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


def advisor_output_schema(advisor: Advisor) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ADVISOR_OUTPUT_REQUIRED_KEYS,
        "properties": {
            "advisor_id": {"type": "string", "const": advisor.advisor_id},
            "advisor_name": {"type": "string", "const": advisor.name},
            "problem_reframe": {"type": "string"},
            "core_judgment": {"type": "string"},
            "decision_mode": {
                "type": "string",
                "enum": [
                    "focus",
                    "cut",
                    "build",
                    "wait",
                    "invest",
                    "redesign",
                    "simplify",
                    "integrate",
                ],
            },
            "recommended_actions": string_array_schema("最多 3 条可执行动作", max_items=3),
            "what_to_cut": string_array_schema("应该停止、删除或避免的东西"),
            "non_negotiables": string_array_schema("不可妥协条件"),
            "supporting_logic": string_array_schema("支撑判断的逻辑"),
            "key_risks": string_array_schema("关键风险"),
            "assumptions": string_array_schema("关键假设"),
            "open_questions": string_array_schema("还需要确认的问题"),
            "success_metrics": string_array_schema("判断是否成功的指标"),
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "limits": string_array_schema("当前视角的失效边界"),
        },
    }


def arbiter_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "problem_definition",
            "consensus",
            "key_disagreements",
            "primary_recommendation",
            "backup_recommendation",
            "do_not_do",
            "next_steps_7d",
            "next_steps_30d",
            "leading_metrics",
            "risk_triggers",
            "confidence",
        ],
        "properties": {
            "problem_definition": {"type": "string"},
            "consensus": string_array_schema("顾问共识"),
            "key_disagreements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["topic", "advisors", "summary", "source_of_conflict"],
                    "properties": {
                        "topic": {"type": "string"},
                        "advisors": string_array_schema("相关顾问"),
                        "summary": {"type": "string"},
                        "source_of_conflict": {"type": "string"},
                    },
                },
            },
            "primary_recommendation": {
                "type": "object",
                "additionalProperties": False,
                "required": ["summary", "why", "conditions"],
                "properties": {
                    "summary": {"type": "string"},
                    "why": {"type": "string"},
                    "conditions": string_array_schema("主建议成立前提"),
                },
            },
            "backup_recommendation": {
                "type": "object",
                "additionalProperties": False,
                "required": ["summary", "switch_conditions"],
                "properties": {
                    "summary": {"type": "string"},
                    "switch_conditions": string_array_schema("切换条件"),
                },
            },
            "do_not_do": string_array_schema("明确不建议做的事"),
            "next_steps_7d": string_array_schema("未来 7 天动作"),
            "next_steps_30d": string_array_schema("未来 30 天动作"),
            "leading_metrics": string_array_schema("优先观察的指标"),
            "risk_triggers": string_array_schema("风险触发器"),
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
        },
    }


def extract_response_text(payload: dict[str, Any]) -> str:
    direct_text = payload.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text

    texts: list[str] = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text_value = content.get("text")
            if isinstance(text_value, str):
                texts.append(text_value)
            alt_text = content.get("output_text")
            if isinstance(alt_text, str):
                texts.append(alt_text)

    merged = "".join(texts).strip()
    if not merged:
        raise ValueError("接口返回中没有可解析的文本输出。")
    return merged


def api_headers(api_key: str, client_request_id: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-Client-Request-Id": client_request_id,
    }
    organization = os.getenv("OPENAI_ORGANIZATION")
    project = os.getenv("OPENAI_PROJECT")
    if organization:
        headers["OpenAI-Organization"] = organization
    if project:
        headers["OpenAI-Project"] = project
    return headers


def maybe_reasoning_config(reasoning_effort: str | None) -> dict[str, Any] | None:
    if not reasoning_effort or reasoning_effort == "none":
        return None
    return {"effort": reasoning_effort}


def call_responses_api(
    *,
    api_key: str,
    model: str,
    instructions: str,
    input_text: str,
    schema_name: str,
    schema: dict[str, Any],
    timeout_seconds: int,
    base_url: str,
    reasoning_effort: str | None,
) -> tuple[dict[str, Any], str, dict[str, str], str]:
    client_request_id = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "input": input_text,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    }

    reasoning = maybe_reasoning_config(reasoning_effort)
    if reasoning:
        payload["reasoning"] = reasoning

    req = request.Request(
        url=f"{base_url.rstrip('/')}/responses",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=api_headers(api_key, client_request_id),
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
            response_payload = json.loads(raw)
            response_headers = {key: value for key, value in resp.headers.items()}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail_payload = json.loads(detail)
            message = detail_payload.get("error", {}).get("message", detail)
        except json.JSONDecodeError:
            message = detail
        raise RuntimeError(f"OpenAI 接口返回 HTTP {exc.code}: {message}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI 接口请求失败: {exc.reason}") from exc

    response_text = extract_response_text(response_payload)
    return response_payload, response_text, response_headers, client_request_id


def advisor_instructions(advisor: Advisor) -> str:
    base_prompt = load_prompt_template("advisor.md")
    skill_text = load_skill_text(advisor.skill)
    return f"""{base_prompt}

## 当前顾问 skill

下面是 {advisor.name} 对应的完整 skill，请严格据此工作：

{skill_text}
"""


def run_single_advisor(
    advisor: Advisor,
    *,
    run_dir: Path,
    api_key: str,
    model: str,
    base_url: str,
    timeout_seconds: int,
    reasoning_effort: str | None,
) -> dict[str, Any]:
    prompt_path = run_dir / "advisor-prompts" / f"{advisor.advisor_id}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"缺少顾问任务包: {prompt_path}")

    response_payload, response_text, response_headers, client_request_id = call_responses_api(
        api_key=api_key,
        model=model,
        instructions=advisor_instructions(advisor),
        input_text=read_text(prompt_path),
        schema_name=f"{advisor.advisor_id}_advisor_output",
        schema=advisor_output_schema(advisor),
        timeout_seconds=timeout_seconds,
        base_url=base_url,
        reasoning_effort=reasoning_effort,
    )

    output_payload = json.loads(response_text)
    problems = validate_advisor_output(output_payload)
    if problems:
        raise ValueError(f"{advisor.advisor_id} 输出校验失败: {', '.join(problems)}")

    write_json(run_dir / "advisor-outputs" / f"{advisor.advisor_id}.json", output_payload)
    write_json(
        run_dir / "api-responses" / f"{advisor.advisor_id}.response.json",
        {
            "kind": "advisor",
            "advisor_id": advisor.advisor_id,
            "model": model,
            "requested_at": now_iso(),
            "client_request_id": client_request_id,
            "response_headers": response_headers,
            "response_body": response_payload,
        },
    )
    return {
        "advisor_id": advisor.advisor_id,
        "advisor_name": advisor.name,
        "output_path": str(run_dir / "advisor-outputs" / f"{advisor.advisor_id}.json"),
    }


def run_advisors(
    run_dir: Path,
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
    reasoning_effort: str | None,
    max_workers: int,
    force: bool,
) -> list[dict[str, Any]]:
    api_key = require_api_key()
    advisors = load_advisors()
    request_payload = read_json(run_dir / "request.normalized.json")
    selected_ids: list[str] = request_payload["selected_advisors"]

    queue: list[Advisor] = []
    skipped: list[dict[str, Any]] = []
    for advisor_id in selected_ids:
        advisor = advisors[advisor_id]
        output_path = run_dir / "advisor-outputs" / f"{advisor_id}.json"
        if output_path.exists() and not force:
            payload = read_json(output_path)
            if payload.get("core_judgment"):
                skipped.append(
                    {
                        "advisor_id": advisor_id,
                        "advisor_name": advisor.name,
                        "status": "skipped",
                    }
                )
                continue
        queue.append(advisor)

    results = list(skipped)
    if not queue:
        return results

    worker_count = max(1, min(max_workers, len(queue)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(
                run_single_advisor,
                advisor,
                run_dir=run_dir,
                api_key=api_key,
                model=model,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                reasoning_effort=reasoning_effort,
            ): advisor
            for advisor in queue
        }
        for future in concurrent.futures.as_completed(future_map):
            advisor = future_map[future]
            result = future.result()
            result["status"] = "completed"
            results.append(result)
            print(f"顾问完成：{advisor.name}")

    write_json(
        run_dir / "artifacts" / "advisor-run.json",
        {
            "model": model,
            "base_url": base_url,
            "reasoning_effort": reasoning_effort,
            "results": results,
            "finished_at": now_iso(),
        },
    )
    return results


def arbiter_instructions() -> str:
    base_prompt = load_prompt_template("arbiter.md")
    report_template = read_text(ROOT / "templates" / "final-report-template.md")
    return f"""{base_prompt}

## 最终报告模板

{report_template}
"""


def render_final_report_markdown(report: dict[str, Any]) -> str:
    disagreement_lines: list[str] = []
    for item in report["key_disagreements"]:
        advisors = "、".join(item["advisors"])
        disagreement_lines.append(
            f"- 主题：{item['topic']}\n"
            f"  - 顾问：{advisors}\n"
            f"  - 分歧：{item['summary']}\n"
            f"  - 来源：{item['source_of_conflict']}"
        )

    return f"""# 最终报告

## 1. 问题定义

{report["problem_definition"]}

## 2. 顾问共识

{render_bullets(report["consensus"])}

## 3. 关键分歧

{chr(10).join(disagreement_lines) if disagreement_lines else "- 暂无重大分歧"}

## 4. 主建议

- 建议：{report["primary_recommendation"]["summary"]}
- 原因：{report["primary_recommendation"]["why"]}
- 成立前提：
{render_bullets(report["primary_recommendation"]["conditions"])}

## 5. 备选建议

- 建议：{report["backup_recommendation"]["summary"]}
- 切换条件：
{render_bullets(report["backup_recommendation"]["switch_conditions"])}

## 6. 明确不建议做的事

{render_bullets(report["do_not_do"])}

## 7. 下一步动作

### 未来 7 天

{render_bullets(report["next_steps_7d"])}

### 未来 30 天

{render_bullets(report["next_steps_30d"])}

### 优先观察指标

{render_bullets(report["leading_metrics"])}

## 8. 风险与触发器

{render_bullets(report["risk_triggers"])}

## 9. 置信度

- {report["confidence"]}
"""


def run_arbiter(
    run_dir: Path,
    *,
    model: str,
    base_url: str,
    timeout_seconds: int,
    reasoning_effort: str | None,
) -> dict[str, Any]:
    api_key = require_api_key()
    request_payload, advisor_outputs = build_arbiter_inputs(run_dir)
    prompt_text = render_arbiter_prompt(request_payload, advisor_outputs)

    response_payload, response_text, response_headers, client_request_id = call_responses_api(
        api_key=api_key,
        model=model,
        instructions=arbiter_instructions(),
        input_text=prompt_text,
        schema_name="arbiter_final_report",
        schema=arbiter_output_schema(),
        timeout_seconds=timeout_seconds,
        base_url=base_url,
        reasoning_effort=reasoning_effort,
    )

    report_payload = json.loads(response_text)
    write_json(run_dir / "artifacts" / "final-report.json", report_payload)
    write_text(run_dir / "artifacts" / "final-report.md", render_final_report_markdown(report_payload))
    write_json(
        run_dir / "api-responses" / "arbiter.response.json",
        {
            "kind": "arbiter",
            "model": model,
            "requested_at": now_iso(),
            "client_request_id": client_request_id,
            "response_headers": response_headers,
            "response_body": response_payload,
        },
    )
    return report_payload


def run_all(
    request_path: Path,
    run_dir: Path,
    *,
    advisor_model: str,
    arbiter_model: str,
    base_url: str,
    timeout_seconds: int,
    reasoning_effort: str | None,
    max_workers: int,
    force: bool,
) -> None:
    prepare_run(request_path, run_dir)
    run_advisors(
        run_dir,
        model=advisor_model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        reasoning_effort=reasoning_effort,
        max_workers=max_workers,
        force=force,
    )
    run_arbiter(
        run_dir,
        model=arbiter_model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        reasoning_effort=reasoning_effort,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="六大师多顾问系统 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-request", help="生成请求模板")
    init_parser.add_argument("--output", type=Path, required=True, help="输出 JSON 文件路径")

    prepare_parser = subparsers.add_parser("prepare-run", help="生成顾问运行包")
    prepare_parser.add_argument("--input", type=Path, required=True, help="请求 JSON 路径")
    prepare_parser.add_argument("--run-dir", type=Path, help="运行目录")
    prepare_parser.add_argument("--name", help="运行名称，仅在未传 run-dir 时使用")

    run_advisors_parser = subparsers.add_parser("run-advisors", help="真实调用模型并回填顾问输出")
    run_advisors_parser.add_argument("--run-dir", type=Path, required=True, help="运行目录")
    run_advisors_parser.add_argument("--model", default=DEFAULT_ADVISOR_MODEL, help="顾问模型")
    run_advisors_parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI API Base URL")
    run_advisors_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单次请求超时（秒）")
    run_advisors_parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_REASONING_EFFORT,
        choices=["none", "low", "medium", "high"],
        help="推理强度",
    )
    run_advisors_parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS, help="并行顾问数")
    run_advisors_parser.add_argument("--force", action="store_true", help="忽略已有输出并重跑")

    arbiter_parser = subparsers.add_parser("build-arbiter", help="基于顾问输出生成仲裁输入")
    arbiter_parser.add_argument("--run-dir", type=Path, required=True, help="运行目录")

    run_arbiter_parser = subparsers.add_parser("run-arbiter", help="真实调用模型生成最终报告")
    run_arbiter_parser.add_argument("--run-dir", type=Path, required=True, help="运行目录")
    run_arbiter_parser.add_argument("--model", default=DEFAULT_ARBITER_MODEL, help="仲裁模型")
    run_arbiter_parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI API Base URL")
    run_arbiter_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单次请求超时（秒）")
    run_arbiter_parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_REASONING_EFFORT,
        choices=["none", "low", "medium", "high"],
        help="推理强度",
    )

    run_all_parser = subparsers.add_parser("run-all", help="准备运行包、执行顾问并生成最终报告")
    run_all_parser.add_argument("--input", type=Path, required=True, help="请求 JSON 路径")
    run_all_parser.add_argument("--run-dir", type=Path, help="运行目录")
    run_all_parser.add_argument("--name", help="运行名称，仅在未传 run-dir 时使用")
    run_all_parser.add_argument("--advisor-model", default=DEFAULT_ADVISOR_MODEL, help="顾问模型")
    run_all_parser.add_argument("--arbiter-model", default=DEFAULT_ARBITER_MODEL, help="仲裁模型")
    run_all_parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI API Base URL")
    run_all_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单次请求超时（秒）")
    run_all_parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_REASONING_EFFORT,
        choices=["none", "low", "medium", "high"],
        help="推理强度",
    )
    run_all_parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS, help="并行顾问数")
    run_all_parser.add_argument("--force", action="store_true", help="忽略已有输出并重跑")

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

        if args.command == "run-advisors":
            results = run_advisors(
                args.run_dir,
                model=args.model,
                base_url=args.base_url,
                timeout_seconds=args.timeout,
                reasoning_effort=args.reasoning_effort,
                max_workers=args.max_workers,
                force=args.force,
            )
            print(json.dumps(results, ensure_ascii=False, indent=2))
            return 0

        if args.command == "build-arbiter":
            build_arbiter(args.run_dir)
            print(f"已生成仲裁输入：{args.run_dir / 'artifacts' / 'arbiter-prompt.md'}")
            return 0

        if args.command == "run-arbiter":
            report = run_arbiter(
                args.run_dir,
                model=args.model,
                base_url=args.base_url,
                timeout_seconds=args.timeout,
                reasoning_effort=args.reasoning_effort,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0

        if args.command == "run-all":
            run_dir = args.run_dir or default_run_dir(args.name)
            run_all(
                args.input,
                run_dir,
                advisor_model=args.advisor_model,
                arbiter_model=args.arbiter_model,
                base_url=args.base_url,
                timeout_seconds=args.timeout,
                reasoning_effort=args.reasoning_effort,
                max_workers=args.max_workers,
                force=args.force,
            )
            print(f"已完成全流程运行：{run_dir}")
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
