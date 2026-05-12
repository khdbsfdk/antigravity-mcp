"""
실험 3: Orchestration 3패턴 비교 벤치마크
==========================================
동일 작업을 3가지 오케스트레이션 패턴으로 실행하고 비교합니다.

패턴:
  ① Single Agent: 1개 에이전트가 순차 처리
  ② Planner + Executor: 계획 수립 후 실행
  ③ 병렬 Sub-Agent: 독립 작업을 병렬 실행 후 취합

실행 방법 (MCP Agent Pod 내부에서):
  python experiments/orchestration/benchmark.py
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://mcp-llm-service.test.svc.cluster.local:11434/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemma4:26b")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-tools-server.test.svc.cluster.local:8080")

BENCHMARK_TASK = {
    "id": "orch_benchmark",
    "name": "복합 비교 작업 (서울/도쿄 날씨+시간+계산+추천)",
    "prompt": "서울과 도쿄의 현재 날씨를 비교하고, 두 도시의 현재 시간 차이를 계산해서, 여행 추천 문장을 만들어줘.",
}


def mcp_tools_to_openai_format(mcp_tools):
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or f"{tool.name} 도구",
                "parameters": tool.inputSchema if tool.inputSchema else {"type": "object", "properties": {}},
            },
        }
        for tool in mcp_tools
    ]


async def _llm_call(llm_client, messages, tools=None):
    """공통 LLM 호출 래퍼"""
    response = await llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto" if tools else None,
        temperature=0.1,
    )
    return response


async def _execute_tool_calls(session, msg, messages, tool_log):
    """Tool Call 실행 및 메시지 히스토리 업데이트"""
    if not msg.tool_calls:
        return False

    messages.append({
        "role": "assistant",
        "content": msg.content,
        "tool_calls": [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ],
    })

    for tc in msg.tool_calls:
        tool_name = tc.function.name
        try:
            tool_args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            tool_args = {}

        tc_start = time.time()
        try:
            result = await session.call_tool(tool_name, tool_args)
            text = "\n".join(item.text if hasattr(item, "text") else str(item) for item in result.content) if result.content else ""
            success = True
            error = None
        except Exception as e:
            text = f"오류: {e}"
            success = False
            error = str(e)

        tc_elapsed = time.time() - tc_start
        tool_log.append({"tool": tool_name, "args": tool_args, "success": success, "error": error, "elapsed": round(tc_elapsed, 2)})
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": text})

    return True


# ─────────────────────────────────────────────────
# 패턴 ①: Single Agent (순차 처리)
# ─────────────────────────────────────────────────
async def run_single_agent(session, llm_client, openai_tools, task):
    """1개 에이전트가 순차적으로 모든 Tool Call을 처리"""
    messages = [
        {"role": "system", "content": "당신은 MCP 기반 AI 어시스턴트입니다. 도구를 활용하여 정확한 정보를 제공합니다. 한국어로 답변합니다."},
        {"role": "user", "content": task["prompt"]},
    ]

    tool_log = []
    start_time = time.time()

    for _ in range(15):
        response = await _llm_call(llm_client, messages, openai_tools)
        msg = response.choices[0].message

        if response.choices[0].finish_reason == "stop" or not msg.tool_calls:
            elapsed = time.time() - start_time
            return {
                "pattern": "single_agent",
                "success": True,
                "answer": msg.content or "",
                "elapsed_seconds": round(elapsed, 2),
                "tool_calls": tool_log,
                "tool_call_count": len(tool_log),
                "llm_call_count": _ + 1,
                "failure_layer": None,
            }

        await _execute_tool_calls(session, msg, messages, tool_log)

    elapsed = time.time() - start_time
    return {
        "pattern": "single_agent",
        "success": False,
        "answer": "",
        "elapsed_seconds": round(elapsed, 2),
        "tool_calls": tool_log,
        "tool_call_count": len(tool_log),
        "llm_call_count": 15,
        "failure_layer": "LLM (최대 반복 초과)",
    }


# ─────────────────────────────────────────────────
# 패턴 ②: Planner + Executor
# ─────────────────────────────────────────────────
async def run_planner_executor(session, llm_client, openai_tools, task):
    """Planner가 계획 수립 → Executor가 순차 실행"""

    tool_log = []
    start_time = time.time()
    llm_calls = 0

    # Step 1: Planner - 실행 계획 수립
    plan_messages = [
        {"role": "system", "content": """당신은 작업 계획 수립 전문가(Planner)입니다.
사용자의 복합 요청을 분석하여 실행 계획을 JSON 배열로 만들어주세요.

가용 도구: weather(city), get_datetime(timezone), calculator(expression), find_city(city_name), ocr_extract(image_path, directory_path), list_files(directory_path), read_file(file_path)

응답 형식 (반드시 JSON만 출력):
[
  {"step": 1, "tool": "weather", "args": {"city": "Seoul"}, "purpose": "서울 날씨 조회"},
  {"step": 2, "tool": "weather", "args": {"city": "Tokyo"}, "purpose": "도쿄 날씨 조회"}
]"""},
        {"role": "user", "content": task["prompt"]},
    ]

    plan_response = await _llm_call(llm_client, plan_messages)
    llm_calls += 1
    plan_text = plan_response.choices[0].message.content or ""

    # JSON 파싱 시도
    try:
        # JSON 블록 추출
        if "```json" in plan_text:
            plan_text = plan_text.split("```json")[1].split("```")[0].strip()
        elif "```" in plan_text:
            plan_text = plan_text.split("```")[1].split("```")[0].strip()
        plan_steps = json.loads(plan_text)
    except (json.JSONDecodeError, IndexError):
        # 파싱 실패 시 기본 계획
        plan_steps = [
            {"step": 1, "tool": "weather", "args": {"city": "Seoul"}, "purpose": "서울 날씨"},
            {"step": 2, "tool": "weather", "args": {"city": "Tokyo"}, "purpose": "도쿄 날씨"},
            {"step": 3, "tool": "get_datetime", "args": {"timezone": "Asia/Seoul"}, "purpose": "서울 시간"},
            {"step": 4, "tool": "get_datetime", "args": {"timezone": "Asia/Tokyo"}, "purpose": "도쿄 시간"},
        ]

    print(f"    계획 단계: {len(plan_steps)}개")

    # Step 2: Executor - 각 단계 실행
    step_results = []
    for step in plan_steps:
        tool_name = step.get("tool", "")
        tool_args = step.get("args", {})

        tc_start = time.time()
        try:
            result = await session.call_tool(tool_name, tool_args)
            text = "\n".join(item.text if hasattr(item, "text") else str(item) for item in result.content) if result.content else ""
            success = True
            error = None
        except Exception as e:
            text = f"오류: {e}"
            success = False
            error = str(e)

        tc_elapsed = time.time() - tc_start
        tool_log.append({"tool": tool_name, "args": tool_args, "success": success, "error": error, "elapsed": round(tc_elapsed, 2)})
        step_results.append({"step": step.get("step"), "purpose": step.get("purpose"), "result": text[:500]})

    # Step 3: 결과 취합
    summary_messages = [
        {"role": "system", "content": "당신은 데이터를 종합하여 자연스러운 한국어 답변을 작성하는 전문가입니다."},
        {"role": "user", "content": f"원래 질문: {task['prompt']}\n\n수집된 데이터:\n{json.dumps(step_results, ensure_ascii=False, indent=2)}\n\n위 데이터를 바탕으로 자연스러운 답변을 작성하세요."},
    ]
    summary_response = await _llm_call(llm_client, summary_messages)
    llm_calls += 1

    elapsed = time.time() - start_time
    return {
        "pattern": "planner_executor",
        "success": True,
        "answer": summary_response.choices[0].message.content or "",
        "elapsed_seconds": round(elapsed, 2),
        "tool_calls": tool_log,
        "tool_call_count": len(tool_log),
        "llm_call_count": llm_calls,
        "plan_steps": len(plan_steps),
        "failure_layer": None,
    }


# ─────────────────────────────────────────────────
# 패턴 ③: 병렬 Sub-Agent
# ─────────────────────────────────────────────────
async def _sub_agent_task(session, llm_client, openai_tools, sub_prompt, sub_name):
    """독립 sub-agent 실행"""
    messages = [
        {"role": "system", "content": f"당신은 '{sub_name}' 전담 에이전트입니다. 주어진 작업만 정확히 수행하고 결과를 반환하세요. 한국어로 답변합니다."},
        {"role": "user", "content": sub_prompt},
    ]

    tool_log = []
    for _ in range(5):
        response = await _llm_call(llm_client, messages, openai_tools)
        msg = response.choices[0].message

        if response.choices[0].finish_reason == "stop" or not msg.tool_calls:
            return {"sub_agent": sub_name, "result": msg.content or "", "tool_calls": tool_log, "success": True}

        await _execute_tool_calls(session, msg, messages, tool_log)

    return {"sub_agent": sub_name, "result": "", "tool_calls": tool_log, "success": False}


async def run_parallel_subagent(session, llm_client, openai_tools, task):
    """독립 하위 작업을 병렬 실행 후 결과 취합"""

    start_time = time.time()

    # Sub-Agent 정의 (독립 실행 가능한 작업으로 분해)
    sub_tasks = [
        ("서울 날씨 에이전트", "서울의 현재 날씨를 상세히 알려줘"),
        ("도쿄 날씨 에이전트", "도쿄의 현재 날씨를 상세히 알려줘"),
        ("서울 시간 에이전트", "서울(Asia/Seoul)의 현재 시간을 알려줘"),
        ("도쿄 시간 에이전트", "도쿄(Asia/Tokyo)의 현재 시간을 알려줘"),
    ]

    # 병렬 실행
    print(f"    병렬 Sub-Agent {len(sub_tasks)}개 실행...")
    results = await asyncio.gather(*[
        _sub_agent_task(session, llm_client, openai_tools, prompt, name)
        for name, prompt in sub_tasks
    ])

    # 모든 Tool 로그 수집
    all_tool_logs = []
    sub_results_text = []
    for r in results:
        all_tool_logs.extend(r["tool_calls"])
        sub_results_text.append(f"[{r['sub_agent']}]\n{r['result']}")

    # 취합 에이전트
    merge_messages = [
        {"role": "system", "content": "당신은 여러 에이전트의 결과를 종합하여 최종 답변을 만드는 취합 에이전트입니다. 한국어로 답변합니다."},
        {"role": "user", "content": f"원래 질문: {task['prompt']}\n\n각 에이전트 결과:\n" + "\n\n".join(sub_results_text) + "\n\n위 결과를 종합하여 날씨 비교, 시간 차이 계산, 여행 추천 문장을 포함한 답변을 작성하세요."},
    ]
    merge_response = await _llm_call(llm_client, merge_messages)

    elapsed = time.time() - start_time
    return {
        "pattern": "parallel_subagent",
        "success": True,
        "answer": merge_response.choices[0].message.content or "",
        "elapsed_seconds": round(elapsed, 2),
        "tool_calls": all_tool_logs,
        "tool_call_count": len(all_tool_logs),
        "llm_call_count": len(sub_tasks) + 1,  # sub-agents + merge
        "sub_agent_count": len(sub_tasks),
        "failure_layer": None,
    }


def generate_benchmark_report(results, output_path):
    """3패턴 벤치마크 보고서 생성"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# 실험 3: Orchestration 3패턴 비교 벤치마크 결과",
        "",
        f"> 실험 일시: {timestamp}",
        f"> LLM 모델: {LLM_MODEL}",
        f"> 실험 작업: {BENCHMARK_TASK['name']}",
        "",
        "## 벤치마크 비교표",
        "",
        "| 항목 | ① Single Agent | ② Planner+Executor | ③ 병렬 Sub-Agent |",
        "|------|---------------|-------------------|-----------------|",
    ]

    patterns = ["single_agent", "planner_executor", "parallel_subagent"]
    pattern_map = {r["pattern"]: r for r in results}

    metrics = [
        ("성공 여부", lambda r: "✅" if r.get("success") else "❌"),
        ("총 소요 시간", lambda r: f"{r.get('elapsed_seconds', 'N/A')}초"),
        ("Tool 호출 수", lambda r: f"{r.get('tool_call_count', 0)}회"),
        ("LLM 호출 수", lambda r: f"{r.get('llm_call_count', 0)}회"),
        ("Tool 실패 수", lambda r: f"{sum(1 for tc in r.get('tool_calls', []) if not tc.get('success', True))}회"),
        ("실패 레이어", lambda r: r.get("failure_layer", "없음") or "없음"),
    ]

    for name, fn in metrics:
        row = f"| {name} |"
        for p in patterns:
            r = pattern_map.get(p, {})
            row += f" {fn(r)} |"
        lines.append(row)

    lines.append("")

    # 각 패턴 답변
    pattern_labels = ["① Single Agent", "② Planner + Executor", "③ 병렬 Sub-Agent"]
    for p, label in zip(patterns, pattern_labels):
        r = pattern_map.get(p, {})
        lines.append(f"### {label} 답변")
        lines.append("")
        answer = r.get("answer", "(답변 없음)")
        if len(answer) > 1500:
            answer = answer[:1500] + "\n\n... (이하 생략)"
        lines.append("```")
        lines.append(answer)
        lines.append("```")
        lines.append("")

    # 회고
    lines.extend([
        "## \"이 작업엔 이 패턴\" 회고",
        "",
        "### 패턴별 적합한 작업 유형",
        "",
        "| 패턴 | 적합한 작업 | 부적합한 작업 |",
        "|------|-----------|-------------|",
        "| Single Agent | 간단한 단일 도구 작업, 컨텍스트 유지 중요한 대화 | 독립 병렬 가능 작업 |",
        "| Planner+Executor | 명확한 단계가 있는 복합 작업, 순서 의존적 작업 | 즉시 답변 필요한 단순 질문 |",
        "| 병렬 Sub-Agent | 독립적 하위 작업이 많은 경우, 속도가 중요한 경우 | 이전 결과에 의존하는 순차 작업 |",
        "",
    ])

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    return output_path


async def main():
    from mcp.client.sse import sse_client
    from mcp import ClientSession

    print("=" * 60)
    print("  실험 3: Orchestration 3패턴 비교 벤치마크")
    print("=" * 60)

    llm_client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)
    mcp_url = f"{MCP_SERVER_URL.rstrip('/')}/sse"
    all_results = []

    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            openai_tools = mcp_tools_to_openai_format(tools_response.tools)
            print(f"등록된 Tool: {len(openai_tools)}개\n")

            # 패턴 ①
            print("📌 패턴 ①: Single Agent")
            print("-" * 40)
            r1 = await run_single_agent(session, llm_client, openai_tools, BENCHMARK_TASK)
            all_results.append(r1)
            print(f"  → {r1['elapsed_seconds']}초, Tool {r1['tool_call_count']}회, LLM {r1['llm_call_count']}회\n")

            # 패턴 ②
            print("📌 패턴 ②: Planner + Executor")
            print("-" * 40)
            r2 = await run_planner_executor(session, llm_client, openai_tools, BENCHMARK_TASK)
            all_results.append(r2)
            print(f"  → {r2['elapsed_seconds']}초, Tool {r2['tool_call_count']}회, LLM {r2['llm_call_count']}회\n")

            # 패턴 ③
            print("📌 패턴 ③: 병렬 Sub-Agent")
            print("-" * 40)
            r3 = await run_parallel_subagent(session, llm_client, openai_tools, BENCHMARK_TASK)
            all_results.append(r3)
            print(f"  → {r3['elapsed_seconds']}초, Tool {r3['tool_call_count']}회, LLM {r3['llm_call_count']}회\n")

    # 결과 저장
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments", "results")
    os.makedirs(results_dir, exist_ok=True)

    json_path = os.path.join(results_dir, "experiment3_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"💾 JSON 결과: {json_path}")

    report_path = os.path.join(results_dir, "experiment3_report.md")
    generate_benchmark_report(all_results, report_path)
    print(f"📊 벤치마크 보고서: {report_path}")

    print("\n✅ 실험 3 완료!")


if __name__ == "__main__":
    asyncio.run(main())
