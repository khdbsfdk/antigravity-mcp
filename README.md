# 🤖 MCP Test - Model Context Protocol 서버 & 에이전트

MCP(Model Context Protocol) 서버와 LLM 에이전트를 학습하기 위한 프로젝트입니다.

## 📚 MCP란?

MCP는 Anthropic이 개발한 **개방형 표준 프로토콜**로, AI 모델이 외부 도구·데이터·서비스와 상호작용할 수 있게 해줍니다.

```
사용자 질문
    ↓
MCP Client (에이전트)
    ↓  JSON-RPC 2.0 (stdio / HTTP)
MCP Server → Tool 실행 (calculator / datetime / weather / ocr / file)
    ↓
결과를 LLM에 전달
    ↓
최종 자연어 답변
```

---

## 🗂️ 프로젝트 구조

```
mcp_test/
├── README.md
├── requirements.txt             # Python 의존성
├── .env.example                 # 환경변수 템플릿
│
├── server/
│   ├── server.py                # FastMCP 서버 (10개 Tool 등록)
│   └── tools/
│       ├── calculator.py        # Tool 1: 사칙연산 계산기
│       ├── datetime_tool.py     # Tool 2: NTP 기반 날짜/시간 조회
│       ├── weather.py           # Tool 3: 날씨 조회 (OpenWeatherMap)
│       ├── ocr.py               # Tool 4: 이미지 OCR (Google Gemini)
│       ├── openai-ocr.py        # Tool 4 백업: 이전 OpenAI 버전 (미사용)
│       └── file_utils.py        # Tool 5: 파일 읽기/디렉토리 조회
│
├── client/
│   └── agent.py                 # LLM + MCP Tool Call 에이전트
│
├── image_data/                  # OCR 테스트용 이미지 데이터
│
├── experiments/                 # 오케스트레이션 실험
│   ├── experiment_runner.py
│   └── orchestration/
│       ├── benchmark.py
│       └── __init__.py
│
└── deploy/
    ├── Dockerfile               # MCP 서버 컨테이너
    ├── Dockerfile.client        # MCP 에이전트 컨테이너
    ├── Dockerfile.vllm          # vLLM 추론 서버 (V100 GPU)
    ├── deploy.sh                # OpenShift 배포 스크립트
    └── openshift/
        ├── mcp-server-deployment.yaml  # MCP 서버 + Service + Route
        ├── mcp-configmap.yaml          # 공통 환경변수 ConfigMap
        ├── agent-deployment.yaml       # 에이전트 Deployment
        └── ollama-test-deployment.yaml # Ollama (gemma4:26b) Deployment
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
# LLM (Ollama)
OLLAMA_BASE_URL=http://mcp-llm-service.test.svc.cluster.local:11434/v1
OLLAMA_API_KEY=ollama
LLM_MODEL=gemma4:26b

# 날씨 API 키 (https://openweathermap.org 무료 가입 후 발급)
OPENWEATHER_API_KEY=xxxxxxxx

# OCR (Google AI Studio - Gemini)
GEMINI_API_KEY=xxxxxxxx
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
| `ocr_extract` | 이미지 OCR 텍스트 추출 | `image_path="/data/img.jpg"` |
| `read_file` | 텍스트 파일 읽기 | `file_path="/data/result.txt"` |
| `list_files` | 디렉토리 파일 목록 | `directory_path="/data/images"` |

### 🔍 OCR Tool 상세

OCR 기능은 **Google AI Studio (Gemini 2.5 Flash Lite)** 모델을 사용하여 이미지에서 텍스트를 추출합니다.

> ⚠️ **변경 이력**: 초기에는 OpenAI GPT-4o Vision API를 사용했으나, API 키 만료로 인해 Google Gemini로 전환하였습니다. 이전 코드는 `openai-ocr.py`에 백업되어 있습니다.

**두 가지 모드:**
- **단일 이미지 모드**: `image_path`에 이미지 파일 경로 지정
- **디렉토리 모드**: `directory_path`에 폴더 경로 지정 → 모든 이미지를 일괄 OCR

```
👤 사용자: /data/images 폴더의 이미지들을 OCR 처리해줘
🤖 어시스턴트:
  🔧 Tool 호출: ocr_extract(directory_path='/data/images')
  📋 결과: ✅ OCR 완료! 3개 이미지 → 성공 3개
           💾 결과 파일: images/ocr_result.txt
```

**필요한 환경변수:**
- `GEMINI_API_KEY`: Google AI Studio API 키

**지원 이미지 형식:** jpg, jpeg, png

> ℹ️ 무료 티어 속도 제한(RPM) 준수를 위해 이미지 한 장당 4초 간격으로 처리됩니다.

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

## ☁️ OpenShift 배포

### 아키텍처

```
[사용자 터미널]
    oc exec -it deployment/mcp-agent -n test -- python client/agent.py
                    │
                    ▼
         [mcp-agent Pod] (test ns)
         gemma4:26b 모델에 질문
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
[mcp-llm-service:11434]  [mcp-tools-server:8080]
 Ollama + gemma4:26b      SSE Transport + 10 Tools
 V100 32GB GPU            calculator / datetime /
                          weather / ocr / file_utils
```

### 배포 순서

```bash
# 1. ConfigMap 적용
oc apply -f deploy/openshift/mcp-configmap.yaml

# 2. Ollama (gemma4) 배포 (모델 로드 시간 소요)
oc apply -f deploy/openshift/ollama-test-deployment.yaml

# Ollama 상태 확인 (Running 상태 대기)
oc get pods -n test -w

# 3. MCP 서버 배포
oc apply -f deploy/openshift/mcp-server-deployment.yaml

# 4. 에이전트 배포
oc apply -f deploy/openshift/agent-deployment.yaml

# 5. Route 확인
oc get route -n test

# 6. 에이전트 실행 (대화형)
oc exec -it deployment/mcp-agent -n test -- python client/agent.py
```

### 이미지 빌드 (OpenShift BuildConfig)

```bash
# MCP 서버 이미지 빌드
oc start-build mcp-tools-server --from-dir=. -n test --follow

# MCP 에이전트 이미지 빌드
oc start-build mcp-agent --from-dir=. -n test --follow
```

### OCR 이미지 데이터 전송

```bash
# bastion에서 이미지를 Pod 내부로 복사
oc cp ./image_data/ mcp-tools-server-<pod-id>:/data/images -n test
```

### V100 특이사항

> ⚠️ **중요**: NVIDIA V100은 `bfloat16`을 지원하지 않습니다.  
> vLLM 실행 시 반드시 `--dtype float16` 옵션을 사용해야 합니다.

| 항목 | 값 |
|------|-----|
| GPU 아키텍처 | Volta (Compute Capability 7.0) |
| 지원 dtype | `float16` (bfloat16 ❌) |
| 현재 사용 모델 | `gemma4:26b` (Ollama) |
| GPU VRAM | 32GB (Tesla V100-SXM2-32GB) |

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
  {"name":"calculator","description":"수식 계산","inputSchema":{...}},
  {"name":"ocr_extract","description":"이미지 OCR","inputSchema":{...}}
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
google-genai     # Google AI Studio (Gemini OCR)
requests         # HTTP 요청 (날씨 API)
httpx            # HTTP 클라이언트
python-dotenv    # 환경변수 관리
ntplib           # NTP 시간 조회
pytz             # 타임존 처리
Pillow           # 이미지 처리
uvicorn          # ASGI 서버
anyio            # 비동기 유틸리티
```

---

## 🛠️ 추가 확장 아이디어

- 🗄️ **데이터베이스 Tool**: SQL 쿼리 실행 (PostgreSQL, SQLite)
- 🔍 **웹 검색 Tool**: 인터넷 검색 결과 조회
- 📧 **이메일 Tool**: 이메일 발송
- 🗺️ **지도 Tool**: 경로 안내, 장소 검색

---

## 📖 참고 자료

- [MCP 공식 문서](https://modelcontextprotocol.io)
- [FastMCP 문서](https://gofastmcp.com)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Google AI Studio](https://aistudio.google.com)
- [Ollama 문서](https://ollama.com)
- [OpenWeatherMap API](https://openweathermap.org/api)
