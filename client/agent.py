"""
MCP Agent Client - LLM + Tool Call 에이전트
============================================
MCP 서버에 연결하여 LLM이 Tool을 호출할 수 있도록 하는 에이전트입니다.

[ 작동 원리 ]
  사용자 입력
    → LLM (Ollama/OpenAI 호환 API)
    → Tool Call 요청 감지
    → MCP 서버에 Tool 실행 요청 (HTTP via streamablehttp)
    → 결과를 LLM에 다시 전달
    → 최종 자연어 답변

[ Transport 모드 ]
  - TRANSPORT=stdio  : MCP 서버를 subprocess로 실행 (로컬 개발용)
  - TRANSPORT=http   : MCP 서버 HTTP 엔드포인트에 연결 (OpenShift 배포, 기본값)

[ 환경변수 (.env) ]
  # LLM 설정 (Ollama)
  OLLAMA_BASE_URL   : Ollama 서버 주소 (예: http://ollama-service:11434/v1)
  LLM_MODEL         : 사용할 모델명 (예: gemma3:4b, gemma4, llama3.2)

  # MCP 서버 연결 (HTTP 모드)
  MCP_SERVER_URL    : MCP 서버 HTTP 주소 (예: http://mcp-tools-server:8080)
  TRANSPORT         : 연결 방식 (http | stdio, 기본: http)

  # OpenWeatherMap
  OPENWEATHER_API_KEY : 날씨 API 키
"""

import asyncio
import json
import logging
import os
import sys

from dotenv import load_dotenv
from openai import AsyncOpenAI

# 환경변수 로드
load_dotenv()

# ─────────────────────────────────────────────────
# 로깅
# ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp-agent")


# ─────────────────────────────────────────────────
# 환경변수 설정
# ─────────────────────────────────────────────────
# --- LLM (Ollama) ---
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama-service:11434/v1")
LLM_MODEL       = os.environ.get("LLM_MODEL", "gemma4:26b")
# Ollama는 API 키가 필요 없지만 openai 라이브러리는 값을 요구함
OLLAMA_API_KEY  = os.environ.get("OLLAMA_API_KEY", "ollama")

# --- MCP 서버 ---
# HTTP 모드: MCP 서버 파드에 직접 연결
MCP_SERVER_URL  = os.environ.get("MCP_SERVER_URL", "http://mcp-tools-server:8080")
# 연결 방식: http (OpenShift) 또는 stdio (로컬 개발)
TRANSPORT       = os.environ.get("TRANSPORT", "http").lower()

# stdio 모드에서 사용할 MCP 서버 스크립트 경로
_THIS_DIR        = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT    = os.path.dirname(_THIS_DIR)
MCP_SERVER_SCRIPT = os.path.join(_PROJECT_ROOT, "server", "server.py")


# ─────────────────────────────────────────────────
# 에이전트 하네스 (Agent Harness)
# ─────────────────────────────────────────────────
# 하네스는 LLM이 도구를 올바른 순서로 사용하고,
# 복잡한 워크플로우를 자동으로 체이닝할 수 있도록
# 제어하는 시스템 프롬프트입니다.
# ─────────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 MCP(Model Context Protocol) 기반 AI 어시스턴트입니다.
사용자의 자연어 요청을 이해하고, 적절한 도구(Tool)를 자동으로 선택·조합하여 작업을 수행합니다.

═══════════════════════════════════════════════════
  📋 사용 가능한 도구 (Tools)
═══════════════════════════════════════════════════

[그룹 1: 수학 계산]
- calculator(expression): 수식 계산 (예: "3 + 4 * 2", "sqrt(144)")
- calculator_two(a, b, operation): 두 숫자 직접 계산

[그룹 2: 날짜/시간]
- get_datetime(timezone): 현재 날짜/시간 조회 (NTP 기반)
- get_timezones(region): 타임존 목록 조회

[그룹 3: 날씨]
- weather(city, units): 도시 날씨 조회
- find_city(city_name): 도시 위치 검색

[그룹 4: OCR - 이미지 텍스트 추출]
- ocr_extract(image_path, directory_path, output_path): 이미지에서 텍스트 추출 (GPT-4o Vision)
  · image_path: 단일 이미지 파일 경로
  · directory_path: 이미지 폴더 경로 (일괄 처리)
  · output_path: 결과 저장 경로 (선택, 비워두면 자동 생성)

[그룹 5: 파일 시스템]
- read_file(file_path): 텍스트 파일 읽기
- list_files(directory_path, extension_filter): 디렉토리 파일 목록 조회

═══════════════════════════════════════════════════
  🔗 워크플로우 체이닝 규칙 (Harness)
═══════════════════════════════════════════════════

★ 워크플로우 A: "OCR → PPT용 텍스트 정리" 자동화 ★
사용자가 이미지에서 텍스트를 추출하거나 PPT/문서 준비를 요청할 때:

  1단계: list_files(directory_path)로 디렉토리 내 이미지 파일 존재 여부 확인
  2단계: ocr_extract(directory_path=...)로 이미지에서 텍스트 추출
  3단계: read_file(file_path=<결과파일>)로 추출된 텍스트 읽기
  4단계: 읽은 텍스트를 PPT에 적합한 구조(제목/본문/글머리기호)로 정리하여 답변

  ⚠️ 반드시 1→2→3→4 순서를 따르세요.
  ⚠️ 각 단계의 결과를 확인한 후 다음 단계로 진행하세요.
  ⚠️ 2단계에서 output_file 경로가 반환되면, 3단계에서 그 경로를 사용하세요.

★ 워크플로우 B: 단일 이미지 OCR ★
  1단계: ocr_extract(image_path=...)로 텍스트 추출
  2단계: 추출된 텍스트를 자연스럽게 설명

★ 워크플로우 C: 일반 도구 사용 ★
  - 계산, 날씨, 시간 등은 해당 도구를 직접 호출

═══════════════════════════════════════════════════
  🛡️ 오류 처리 및 가드레일
═══════════════════════════════════════════════════

1. 도구 호출 실패 시: 오류 메시지를 사용자에게 설명하고 대안을 제시하세요.
2. 디렉토리에 이미지가 없을 때: 사용자에게 지원 형식(jpg,png 등)과 경로를 안내하세요.
3. API 키 오류 시: "API 키 설정이 필요합니다"라고 안내하세요.
4. 파일을 찾을 수 없을 때: 정확한 경로를 다시 확인해달라고 요청하세요.
5. 한 번에 하나의 워크플로우만 실행하세요. 여러 워크플로우를 동시에 실행하지 마세요.

═══════════════════════════════════════════════════
  📝 응답 규칙
═══════════════════════════════════════════════════

- 항상 한국어로 답변합니다.
- 도구를 사용한 경우, 결과를 자연스러운 문장으로 설명합니다.
- OCR 결과를 PPT용으로 정리할 때는 마크다운 형식으로 구조화합니다:
  # 슬라이드 제목
  ## 소제목
  - 핵심 내용 1
  - 핵심 내용 2
- 계산 결과는 정확히 표시합니다.
- 날씨/시간 정보는 출처도 함께 알려줍니다.
"""



# ─────────────────────────────────────────────────
# MCP Tool → OpenAI Tool 포맷 변환
# ─────────────────────────────────────────────────
def mcp_tools_to_openai_format(mcp_tools) -> list[dict]:
    """MCP Tool 정의를 OpenAI Chat Completions API의 tools 포맷으로 변환합니다."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or f"{tool.name} 도구",
                "parameters": tool.inputSchema if tool.inputSchema else {
                    "type": "object",
                    "properties": {},
                },
            },
        }
        for tool in mcp_tools
    ]


# ─────────────────────────────────────────────────
# 핵심 에이전트 루프 (공통)
# ─────────────────────────────────────────────────
async def run_agent_turn(
    session,
    llm_client: AsyncOpenAI,
    messages: list[dict],
    available_tools: list[dict],
) -> str:
    """
    단일 에이전트 턴을 처리합니다.
    LLM이 Tool Call을 요청하면 MCP 서버에서 실행하고 결과를 다시 LLM에게 전달합니다.
    여러 번의 Tool Call도 루프로 처리합니다.
    """
    MAX_ITERATIONS = 10

    for iteration in range(MAX_ITERATIONS):
        logger.debug(f"[turn] iter={iteration}")

        # ① LLM 호출
        response = await llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=available_tools if available_tools else None,
            tool_choice="auto" if available_tools else None,
            temperature=0.1,
        )

        msg          = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        # ② 완료 (Tool Call 없음)
        if finish_reason == "stop" or not msg.tool_calls:
            return msg.content or ""

        # ③ Tool Call 발생 → 히스토리에 assistant 메시지 추가
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        # ④ 각 Tool 실행
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            arg_str = ", ".join(f"{k}={v!r}" for k, v in tool_args.items())
            print(f"\n  🔧 Tool 호출: {tool_name}({arg_str})")

            try:
                result = await session.call_tool(tool_name, tool_args)
                tool_result_text = (
                    "\n".join(
                        item.text if hasattr(item, "text") else str(item)
                        for item in result.content
                    )
                    if result.content else "결과 없음"
                )
            except Exception as e:
                tool_result_text = f"Tool 실행 오류: {e}"
                logger.error(f"Tool 오류 [{tool_name}]: {e}")

            preview = tool_result_text[:200]
            ellipsis = "..." if len(tool_result_text) > 200 else ""
            print(f"  📋 결과: {preview}{ellipsis}")

            # ⑤ Tool 결과를 히스토리에 추가
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result_text,
            })

    return "최대 반복 횟수(10회)를 초과했습니다."


# ─────────────────────────────────────────────────
# HTTP 모드 메인 (OpenShift - 기본)
# ─────────────────────────────────────────────────
async def run_http_mode():
    """
    MCP 서버에 SSE(Server-Sent Events)로 연결합니다.
    Istio/OSSM 환경에서 streamable-http보다 안정적입니다.
    SSE transport: GET /sse (이벤트 스트림) + POST /messages (요청)
    """
    from mcp.client.sse import sse_client
    from mcp import ClientSession

    mcp_url = f"{MCP_SERVER_URL.rstrip('/')}/sse"
    print(f"🔗 MCP 서버 SSE 연결: {mcp_url}")

    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await _conversation_loop(session)


# ─────────────────────────────────────────────────
# stdio 모드 메인 (로컬 개발용)
# ─────────────────────────────────────────────────
async def run_stdio_mode():
    """
    MCP 서버를 subprocess로 실행하고 stdio로 연결합니다.
    로컬 개발 환경에서 사용합니다.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    if not os.path.exists(MCP_SERVER_SCRIPT):
        print(f"❌ MCP 서버 스크립트를 찾을 수 없습니다: {MCP_SERVER_SCRIPT}")
        sys.exit(1)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[MCP_SERVER_SCRIPT, "--transport", "stdio"],
    )
    print(f"🚀 MCP 서버 subprocess 시작: {MCP_SERVER_SCRIPT}")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await _conversation_loop(session)


# ─────────────────────────────────────────────────
# 대화 루프 (HTTP / stdio 공통)
# ─────────────────────────────────────────────────
async def _conversation_loop(session):
    """MCP 세션이 준비된 후 대화 루프를 실행합니다."""
    from mcp import ClientSession  # 타입 힌트용

    # Tool 목록 조회
    tools_response = await session.list_tools()
    mcp_tools = tools_response.tools
    openai_tools = mcp_tools_to_openai_format(mcp_tools)

    print(f"✅ MCP 서버 연결 완료! 등록된 Tool: {len(mcp_tools)}개")
    for tool in mcp_tools:
        desc = (tool.description or "")[:60]
        print(f"   - {tool.name}: {desc}")

    # LLM 클라이언트 (Ollama OpenAI 호환 API)
    llm_client = AsyncOpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key=OLLAMA_API_KEY,
    )
    print(f"\n🦙 LLM: {LLM_MODEL}  |  엔드포인트: {OLLAMA_BASE_URL}")

    print("\n" + "─" * 60)
    print("  대화를 시작합니다. 종료: 'quit' 또는 '종료' 입력")
    print("─" * 60)

    # 대화 히스토리
    history: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input("\n👤 사용자: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 대화를 종료합니다.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "종료", "나가기"):
            print("\n👋 대화를 종료합니다.")
            break

        history.append({"role": "user", "content": user_input})
        print("\n🤖 어시스턴트: ", end="", flush=True)

        try:
            answer = await run_agent_turn(
                session=session,
                llm_client=llm_client,
                messages=history,
                available_tools=openai_tools,
            )
            print(answer)
            history.append({"role": "assistant", "content": answer})

        except Exception as e:
            err = f"오류 발생: {e}"
            print(err)
            logger.exception("에이전트 오류")
            history.append({"role": "assistant", "content": err})


# ─────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print("  🤖 MCP Agent  –  Ollama + Tool Call")
    print("=" * 60)
    print(f"  Transport : {TRANSPORT.upper()}")
    print(f"  LLM Model : {LLM_MODEL}")
    print(f"  Ollama URL: {OLLAMA_BASE_URL}")
    if TRANSPORT == "http":
        print(f"  MCP Server: {MCP_SERVER_URL}")

    if TRANSPORT == "http":
        await run_http_mode()
    elif TRANSPORT == "stdio":
        await run_stdio_mode()
    else:
        print(f"❌ 알 수 없는 TRANSPORT 값: {TRANSPORT!r}  (http | stdio 중 선택)")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
