# 🤖 MCP Test - Model Context Protocol 서버 & 에이전트

MCP(Model Context Protocol) 서버와 LLM 에이전트를 학습하기 위한 프로젝트입니다.

## 📚 MCP란?

MCP는 Anthropic이 개발한 **개방형 표준 프로토콜**로, AI 모델이 외부 도구·데이터·서비스와 상호작용할 수 있게 해줍니다.

```
사용자 질문
    ↓
MCP Client (에이전트)
    ↓  JSON-RPC 2.0 (stdio / HTTP)
MCP Server → Tool 실행 (calculator / datetime / weather)
    ↓
결과를 LLM에 전달
    ↓
최종 자연어 답변
```

---

## 🗂️ 프로젝트 구조

```
mcp_test/
├── requirements.txt          # Python 의존성
├── .env.example              # 환경변수 예시
│
├── server/                   # ★ MCP 서버 (도구 제공)
│   ├── __init__.py
│   ├── server.py             # FastMCP 진입점 + Tool 등록
│   └── tools/
│       ├── __init__.py
│       ├── calculator.py     # 수식 계산 Tool
│       ├── datetime_tool.py  # NTP 시간 Tool
│       └── weather.py        # OpenWeatherMap 날씨 Tool
│
├── client/                   # ★ MCP 에이전트 (LLM + Tool 호출)
│   ├── __init__.py
│   └── agent.py              # Ollama + MCP 연동 에이전트
│
└── deploy/
    ├── Dockerfile            # mcp-tools-server 이미지
    ├── Dockerfile.client     # mcp-agent 이미지
    └── openshift/
        ├── ollama-test-deployment.yaml   # Ollama LLM Pod
        ├── mcp-server-deployment.yaml    # MCP Tools Server
        └── agent-deployment.yaml         # MCP Agent

```

---

## 🚀 빠른 시작 (로컬 개발)

### 1. 설치

```bash
# 가상환경 생성 (권장)
python -m venv venv
source venv/bin/activate          # Linux/Mac
venv\Scripts\activate             # Windows

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열고 값을 채워주세요:

```dotenv
# LLM API 키 (OpenAI 사용 시)
OPENAI_API_KEY=sk-xxxxxxxx
LLM_MODEL=gpt-4o-mini

# 날씨 API 키 (https://openweathermap.org 무료 가입 후 발급)
OPENWEATHER_API_KEY=xxxxxxxx
```

### 3. MCP 서버 단독 실행 (테스트용)

```bash
# stdio 모드 (MCP Inspector 연결 가능)
python server/server.py

# HTTP 모드 (REST API 방식)
python server/server.py --transport http --port 8080
```

### 4. MCP Inspector로 Tool 테스트

```bash
# MCP Inspector 설치 및 실행
pip install "mcp[cli]"
fastmcp dev server/server.py
```

브라우저에서 `http://localhost:6274` 에 접속하면 각 Tool을 직접 호출할 수 있습니다.

### 5. 에이전트 실행 (LLM + Tool Call)

```bash
python client/agent.py
```

---

## 🔧 등록된 MCP Tools

| Tool 이름 | 설명 | 예시 입력 |
|-----------|------|-----------|
| `calculator` | 수식 계산 | `"3 + 4 * 2"`, `"sqrt(144)"` |
| `calculator_two` | 두 숫자 직접 연산 | `a=10, b=3, operation="/"` |
| `get_datetime` | 인터넷 NTP 기반 현재 시간 | `timezone="Asia/Seoul"` |
| `get_timezones` | 타임존 목록 | `region="Asia"` |
| `weather` | 현재 날씨 조회 | `city="Seoul", units="metric"` |
| `find_city` | 도시 위치 검색 | `city_name="Springfield"` |

---

## 💬 에이전트 사용 예시

```
👤 사용자: 3 더하기 5 곱하기 2는 얼마야?
🤖 어시스턴트:
  🔧 Tool 호출: calculator(expression='3 + 5 * 2')
  📋 결과: ✅ 3 + 5 * 2 = 13
  
  3 + 5 × 2의 결과는 **13**입니다.
  (곱셈이 덧셈보다 우선 계산됩니다: 5 × 2 = 10, 3 + 10 = 13)
```

```
👤 사용자: 지금 서울 시간이 몇 시야?
🤖 어시스턴트:
  🔧 Tool 호출: get_datetime(timezone='Asia/Seoul')
  📋 결과: 🌐 현재 시간 (Asia/Seoul)
           📅 날짜: 2026년 04월 14일 (월요일)
           ⏰ 시간: 11시 15분 30초
  
  현재 서울 시간은 **2026년 4월 14일 월요일, 오전 11시 15분**입니다.
  (NTP 인터넷 서버에서 정확한 시간을 가져왔습니다)
```

```
👤 사용자: 도쿄 날씨 어때?
🤖 어시스턴트:
  🔧 Tool 호출: weather(city='Tokyo', units='metric')
  📋 결과: ⛅ Tokyo, JP 현재 날씨 ...
  
  현재 도쿄의 날씨는 **흐림**, 기온 **18°C** (체감 16°C)이며,
  습도는 65%, 바람은 3.2 m/s 북동풍입니다.
```

---

## ☁️ OpenShift 배포 (V100 GPU)

### 아키텍처

```
[외부 사용자]
    │
    ▼ HTTPS
[OpenShift Route: mcp-tools-server]
    │
    ▼ ClusterIP
[MCP Tools Server Pod] ──── [vLLM Server Pod (V100)]
    │                              │
    │ Tools                        │ LLM Inference
    └── calculator                 └── Qwen2.5-7B-Instruct
    └── datetime                       (float16, 8192 ctx)
    └── weather
```

### 배포 순서

```bash
# 1. vLLM 서버 배포 (모델 다운로드 5~15분 소요)
oc apply -f deploy/openshift/vllm-deployment.yaml

# vLLM 상태 확인 (Running 상태 대기)
oc get pods -n mcp-demo -w

# 2. MCP 서버 배포
oc apply -f deploy/openshift/mcp-server-deployment.yaml
oc apply -f deploy/openshift/mcp-server-service.yaml

# 3. Route 확인
oc get route -n mcp-demo

# 4. (선택) 자동 배포 스크립트
bash deploy/deploy.sh mcp-demo quay.io/myorg
```

### V100 특이사항

> ⚠️ **중요**: NVIDIA V100은 `bfloat16`을 지원하지 않습니다.  
> vLLM 실행 시 반드시 `--dtype float16` 옵션을 사용해야 합니다.

| 항목 | 값 |
|------|----|
| GPU 아키텍처 | Volta (Compute Capability 7.0) |
| 지원 dtype | `float16` (bfloat16 ❌) |
| 권장 모델 (16GB) | `Qwen/Qwen2.5-7B-Instruct` |
| 권장 모델 (32GB) | `meta-llama/Llama-3.1-13B-Instruct` |
| 최대 컨텍스트 | 8192 토큰 (16GB 기준) |

### vLLM 연결로 에이전트 실행

```bash
# vLLM Route 주소 확인
VLLM_ROUTE=$(oc get route vllm-server -n mcp-demo -o jsonpath='{.spec.host}')

# 환경변수 설정 후 에이전트 실행
OPENAI_API_KEY=EMPTY \
OPENAI_BASE_URL="https://${VLLM_ROUTE}/v1" \
LLM_MODEL="qwen2.5-7b" \
python client/agent.py
```

---

## 🔍 MCP 프로토콜 원리

### Transport 방식

| 방식 | 용도 | 특징 |
|------|------|------|
| `stdio` | 로컬 개발, Claude Desktop | 표준 입출력으로 JSON-RPC 통신 |
| `streamable-http` | 원격 서버 (OpenShift) | HTTP 엔드포인트, SSE 스트리밍 |

### JSON-RPC 메시지 흐름

```json
// 1. 클라이언트 → 서버: Tool 목록 요청
{"jsonrpc":"2.0","method":"tools/list","id":1}

// 2. 서버 → 클라이언트: Tool 목록 응답
{"jsonrpc":"2.0","result":{"tools":[
  {"name":"calculator","description":"수식 계산","inputSchema":{...}}
]},"id":1}

// 3. 클라이언트 → 서버: Tool 실행 요청
{"jsonrpc":"2.0","method":"tools/call",
 "params":{"name":"calculator","arguments":{"expression":"3+4"}},"id":2}

// 4. 서버 → 클라이언트: Tool 실행 결과
{"jsonrpc":"2.0","result":{"content":[{"type":"text","text":"✅ 3+4 = 7"}]},"id":2}
```

---

## 📦 의존성

```
mcp[cli]         # MCP SDK (서버/클라이언트)
fastmcp          # FastMCP 프레임워크
openai           # OpenAI / vLLM API 클라이언트
requests         # HTTP 요청 (날씨 API)
python-dotenv    # 환경변수 관리
ntplib           # NTP 시간 조회
pytz             # 타임존 처리
```

---

## 🛠️ 추가 확장 아이디어

- 🗄️ **데이터베이스 Tool**: SQL 쿼리 실행 (PostgreSQL, SQLite)
- 🔍 **웹 검색 Tool**: 인터넷 검색 결과 조회
- 📁 **파일 시스템 Tool**: 파일 읽기/쓰기
- 📧 **이메일 Tool**: 이메일 발송
- 🗺️ **지도 Tool**: 경로 안내, 장소 검색

---

## 📖 참고 자료

- [MCP 공식 문서](https://modelcontextprotocol.io)
- [FastMCP 문서](https://gofastmcp.com)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [vLLM 문서](https://docs.vllm.ai)
- [OpenWeatherMap API](https://openweathermap.org/api)
