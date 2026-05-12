"""
실험 2: Tool 성공 vs 실패 퀼리티 비교 실험 러너
================================================
동일한 작업을 3가지 시나리오로 실행하고 결과를 비교합니다.

시나리오:
  ① MCP 없이 (LLM만)
  ② 잘 만든 MCP (정상 Tool)
  ③ 망가뜨린 MCP (고의 실패 주입)

실행 방법 (MCP Agent Pod 내부에서):
  python experiments/experiment_runner.py
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://mcp-llm-service.test.svc.cluster.local:11434/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemma4:26b")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "ollama")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-tools-server.test.svc.cluster.local:8080")

# 실험 작업들
EXPERIMENT_TASKS = [
    {
        "id": "task1_multi_tool",
        "name": "복합 도구 사용 (날씨+시간+계산)",
        "prompt": "서울 날씨를 알려주고, 오늘 날짜와 3+5*2 계산 결과도 알려줘",
    },
    {
        "id": "task2_ocr",
        "name": "OCR 이미지 텍스트 추출",
        "prompt": "/data/images 디렉토리에 있는 이미지 파일 목록을 보여주고, 첫 번째 이미지에서 텍스트를 추출해줘",
    },
]

SYSTEM_PROMPT_NORMAL = """당신은 MCP 기반 AI 어시스턴트입니다.
사용자의 요청을 이해하고, 적절한 도구(Tool)를 자동으로 선택·조합하여 작업을 수행합니다.
항상 한국어로 답변합니다. 도구를 사용한 경우, 결과를 자연스러운 문장으로 설명합니다."""

SYSTEM_PROMPT_NO_TOOL = """당신은 AI 어시스턴트입니다. 도구 없이 자신의 지식만으로 답변합니다.
항상 한국어로 답변합니다. 모르는 내용은 추측이라고 명시합니다."""


def mcp_tools_to_openai_format(mcp_tools) -> list[dict]:
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


async def run_single_experiment(session, llm_client, task, openai_tools, scenario_name, system_prompt):
    """단일 실험 시나리오 실행"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task["prompt"]},
    ]

    use_tools = scenario_name != "no_mcp"
    tool_calls_log = []
    start_time = time.time()
    MAX_ITERATIONS = 10

    for iteration in range(MAX_ITERATIONS):
        try:
            response = await llm_client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=openai_tools if use_tools else None,
                tool_choice="auto" if use_tools else None,
                temperature=0.1,
            )
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                "scenario": scenario_name,
                "task_id": task["id"],
                "task_name": task["name"],
                "success": False,
                "error": str(e),
                "answer": "",
                "elapsed_seconds": round(elapsed, 2),
                "tool_calls": tool_calls_log,
                "tool_call_count": len(tool_calls_log),
            }

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "stop" or not msg.tool_calls:
            elapsed = time.time() - start_time
            return {
                "scenario": scenario_name,
                "task_id": task["id"],
                "task_name": task["name"],
                "success": True,
                "error": None,
                "answer": msg.content or "",
                "elapsed_seconds": round(elapsed, 2),
                "tool_calls": tool_calls_log,
                "tool_call_count": len(tool_calls_log),
            }

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
                tool_result_text = "\n".join(
                    item.text if hasattr(item, "text") else str(item) for item in result.content
                ) if result.content else "결과 없음"
                tc_success = True
                tc_error = None
            except Exception as e:
                tool_result_text = f"Tool 실행 오류: {e}"
                tc_success = False
                tc_error = str(e)

            tc_elapsed = time.time() - tc_start

            tool_calls_log.append({
                "tool": tool_name,
                "args": tool_args,
                "result_preview": tool_result_text[:300],
                "success": tc_success,
                "error": tc_error,
                "elapsed_seconds": round(tc_elapsed, 2),
            })

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result_text})

    elapsed = time.time() - start_time
    return {
        "scenario": scenario_name,
        "task_id": task["id"],
        "task_name": task["name"],
        "success": False,
        "error": "최대 반복 횟수 초과",
        "answer": "",
        "elapsed_seconds": round(elapsed, 2),
        "tool_calls": tool_calls_log,
        "tool_call_count": len(tool_calls_log),
    }


async def run_no_mcp_experiment(llm_client, task):
    """시나리오 ①: MCP 없이 LLM만으로 답변"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_NO_TOOL},
        {"role": "user", "content": task["prompt"]},
    ]
    start_time = time.time()
    try:
        response = await llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.1,
        )
        elapsed = time.time() - start_time
        return {
            "scenario": "no_mcp",
            "task_id": task["id"],
            "task_name": task["name"],
            "success": True,
            "error": None,
            "answer": response.choices[0].message.content or "",
            "elapsed_seconds": round(elapsed, 2),
            "tool_calls": [],
            "tool_call_count": 0,
        }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "scenario": "no_mcp",
            "task_id": task["id"],
            "task_name": task["name"],
            "success": False,
            "error": str(e),
            "answer": "",
            "elapsed_seconds": round(elapsed, 2),
            "tool_calls": [],
            "tool_call_count": 0,
        }


def generate_comparison_report(all_results, output_path):
    """3가지 시나리오 비교 보고서 생성"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# 실험 2: Tool 성공 vs 실패 품질 비교 결과",
        f"",
        f"> 실험 일시: {timestamp}",
        f"> LLM 모델: {LLM_MODEL}",
        f"",
    ]

    # 작업별로 그룹핑
    tasks = {}
    for r in all_results:
        tid = r["task_id"]
        if tid not in tasks:
            tasks[tid] = {"name": r["task_name"], "results": {}}
        tasks[tid]["results"][r["scenario"]] = r

    for tid, tdata in tasks.items():
        lines.append(f"## 실험 작업: {tdata['name']}")
        lines.append("")
        lines.append("| 항목 | ① MCP 없이 | ② 정상 MCP | ③ 망가뜨린 MCP |")
        lines.append("|------|-----------|-----------|--------------|")

        scenarios = ["no_mcp", "normal_mcp", "broken_mcp"]
        labels = ["① MCP 없이", "② 정상 MCP", "③ 망가뜨린 MCP"]

        # 성공 여부
        row = "| 성공 여부 |"
        for s in scenarios:
            r = tdata["results"].get(s, {})
            row += f" {'✅ 성공' if r.get('success') else '❌ 실패'} |"
        lines.append(row)

        # 응답 시간
        row = "| 응답 시간 |"
        for s in scenarios:
            r = tdata["results"].get(s, {})
            row += f" {r.get('elapsed_seconds', 'N/A')}초 |"
        lines.append(row)

        # Tool 호출 횟수
        row = "| Tool 호출 수 |"
        for s in scenarios:
            r = tdata["results"].get(s, {})
            row += f" {r.get('tool_call_count', 0)}회 |"
        lines.append(row)

        # Tool 실패 수
        row = "| Tool 실패 수 |"
        for s in scenarios:
            r = tdata["results"].get(s, {})
            fails = sum(1 for tc in r.get("tool_calls", []) if not tc.get("success", True))
            row += f" {fails}회 |"
        lines.append(row)

        lines.append("")

        # 각 시나리오 답변 상세
        for s, label in zip(scenarios, labels):
            r = tdata["results"].get(s, {})
            lines.append(f"### {label} 답변")
            lines.append("")
            if r.get("error") and not r.get("success"):
                lines.append(f"> ❌ 오류: {r['error']}")
            answer = r.get("answer", "(답변 없음)")
            # 답변이 너무 길면 잘라냄
            if len(answer) > 1500:
                answer = answer[:1500] + "\n\n... (이하 생략)"
            lines.append(f"```")
            lines.append(answer)
            lines.append(f"```")
            lines.append("")

            # Tool 호출 로그
            if r.get("tool_calls"):
                lines.append(f"**Tool 호출 로그:**")
                for tc in r["tool_calls"]:
                    status = "✅" if tc["success"] else "❌"
                    lines.append(f"- {status} `{tc['tool']}` ({tc['elapsed_seconds']}초) - {tc.get('error', 'OK')}")
                lines.append("")

        lines.append("---")
        lines.append("")

    # 결론
    lines.append("## 분석 및 인사이트")
    lines.append("")
    lines.append("### MCP Tool의 효과")
    lines.append("- **① MCP 없이**: LLM이 자체 지식으로만 답변 → 실시간 데이터(날씨, 시간) 부정확, OCR 불가")
    lines.append("- **② 정상 MCP**: Tool을 통해 정확한 실시간 데이터 제공 → 정확도와 신뢰성 향상")
    lines.append("- **③ 망가뜨린 MCP**: Tool 실패 시 LLM이 오류를 처리하지만 결과 품질 저하")
    lines.append("")

    report = "\n".join(lines)
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    return output_path


async def main():
    from mcp.client.sse import sse_client
    from mcp import ClientSession

    print("=" * 60)
    print("  실험 2: Tool 성공 vs 실패 품질 비교")
    print("=" * 60)

    llm_client = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)
    mcp_url = f"{MCP_SERVER_URL.rstrip('/')}/sse"
    all_results = []

    # ─── 시나리오 ①: MCP 없이 ───
    print("\n📌 시나리오 ①: MCP 없이 (LLM만)")
    print("-" * 40)
    for task in EXPERIMENT_TASKS:
        print(f"  실행: {task['name']}...")
        result = await run_no_mcp_experiment(llm_client, task)
        all_results.append(result)
        print(f"  → {'✅' if result['success'] else '❌'} {result['elapsed_seconds']}초")

    # ─── 시나리오 ②: 정상 MCP ───
    print("\n📌 시나리오 ②: 정상 MCP")
    print("-" * 40)
    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            openai_tools = mcp_tools_to_openai_format(tools_response.tools)
            print(f"  등록된 Tool: {len(openai_tools)}개")

            for task in EXPERIMENT_TASKS:
                print(f"  실행: {task['name']}...")
                result = await run_single_experiment(
                    session, llm_client, task, openai_tools, "normal_mcp", SYSTEM_PROMPT_NORMAL
                )
                all_results.append(result)
                print(f"  → {'✅' if result['success'] else '❌'} {result['elapsed_seconds']}초, Tool호출: {result['tool_call_count']}회")

    # ─── 시나리오 ③: 망가뜨린 MCP ───
    print("\n📌 시나리오 ③: 망가뜨린 MCP (고의 실패 주입)")
    print("-" * 40)

    # MCP_FAILURE_MODE를 설정해서 서버 재배포 대신,
    # 클라이언트 측에서 Tool description을 조작
    broken_tools = []
    for t in openai_tools:
        bt = json.loads(json.dumps(t))  # deep copy
        # 실패 패턴 1: description 조작
        if bt["function"]["name"] == "calculator":
            bt["function"]["description"] = "날씨 정보를 조회합니다. city 파라미터에 도시명을 입력하세요."
        elif bt["function"]["name"] == "weather":
            bt["function"]["description"] = "수학 수식을 계산합니다. expression 파라미터에 수식을 입력하세요."
        elif bt["function"]["name"] == "get_datetime":
            bt["function"]["description"] = "이미지에서 텍스트를 추출합니다."
        elif bt["function"]["name"] == "ocr_extract":
            bt["function"]["description"] = "현재 날짜와 시간을 조회합니다."
        broken_tools.append(bt)

    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            for task in EXPERIMENT_TASKS:
                print(f"  실행: {task['name']}...")
                result = await run_single_experiment(
                    session, llm_client, task, broken_tools, "broken_mcp", SYSTEM_PROMPT_NORMAL
                )
                all_results.append(result)
                print(f"  → {'✅' if result['success'] else '❌'} {result['elapsed_seconds']}초, Tool호출: {result['tool_call_count']}회")

    # ─── 결과 저장 ───
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(results_dir, exist_ok=True)

    # JSON 원본
    json_path = os.path.join(results_dir, "experiment2_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 JSON 결과: {json_path}")

    # 비교 보고서
    report_path = os.path.join(results_dir, "experiment2_report.md")
    generate_comparison_report(all_results, report_path)
    print(f"📊 비교 보고서: {report_path}")

    print("\n✅ 실험 2 완료!")


if __name__ == "__main__":
    asyncio.run(main())
