# MCP 서버 OpenShift 구축 가이드 (Part 1: 구조 & 파일)

## 1. 프로젝트 파일 Tree 구조

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

## 2. 핵심 파일 내용

### 2-1. requirements.txt
```
mcp[cli]>=1.0
fastmcp
openai>=1.0
requests
python-dotenv
ntplib
pytz
uvicorn
starlette
httpx
```

### 2-2. deploy/Dockerfile (MCP Tools Server)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ ./server/
COPY client/ ./client/
ENV PYTHONPATH=/app
EXPOSE 8080
CMD ["python", "server/server.py", "--transport", "http", "--port", "8080"]
```

### 2-3. deploy/Dockerfile.client (MCP Agent)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ ./server/
COPY client/ ./client/
ENV PYTHONPATH=/app
# sleep infinity로 대기 → oc exec으로 직접 실행
CMD ["sleep", "infinity"]
```

### 2-4. 완성된 ConfigMap (mcp-config)
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mcp-config
  namespace: test
data:
  TRANSPORT: "http"
  MCP_HOST: "0.0.0.0"
  MCP_PORT: "8080"
  # ★ 네임스페이스 내부 DNS 풀주소 사용
  MCP_SERVER_URL: "http://mcp-tools-server.test.svc.cluster.local:8080"
  OLLAMA_BASE_URL: "http://mcp-llm-service.test.svc.cluster.local:11434/v1"
  OLLAMA_MODEL: "gemma4:26b"
  LLM_MODEL: "gemma4:26b"
  LOG_LEVEL: "INFO"
```

### 2-5. Ollama Deployment (mcp-llm-gemma4)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-llm-gemma4
  namespace: test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-llm
  template:
    metadata:
      labels:
        app: mcp-llm
    spec:
      serviceAccountName: mcp-server-sa   # ★ anyuid SCC 부여된 SA
      securityContext:
        runAsUser: 0                        # ★ Ollama는 root 필요
      containers:
        - name: ollama
          image: ollama/ollama:latest
          ports:
            - containerPort: 11434
          env:
            - name: HOME
              value: "/ollama"
            - name: OLLAMA_MODELS
              value: "/ollama/models"
            - name: OLLAMA_HOST
              value: "0.0.0.0"             # ★ 반드시 0.0.0.0 (외부 접근용)
            - name: OLLAMA_KEEP_ALIVE
              value: "-1"                   # 모델 메모리 상주 (무제한)
          resources:
            limits:
              nvidia.com/gpu: "1"          # ★ V100 GPU 1개
          volumeMounts:
            - name: ollama4-storage
              mountPath: /ollama
      volumes:
        - name: ollama4-storage
          persistentVolumeClaim:
            claimName: pvc-gemma4          # ★ 모델 가중치 PVC
      tolerations:
        - key: "nvidia.com/gpu"
          operator: "Exists"
          effect: "NoSchedule"
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-llm-service
  namespace: test
spec:
  selector:
    app: mcp-llm
  ports:
    - port: 11434
      targetPort: 11434
  type: ClusterIP
```

### 2-6. MCP Tools Server Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-tools-server
  namespace: test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-tools-server
  template:
    metadata:
      labels:
        app: mcp-tools-server
      annotations:
        sidecar.istio.io/inject: "false"   # ★ Istio mTLS 비활성화 (421 방지)
    spec:
      containers:
        - name: mcp-tools-server
          image: image-registry.openshift-image-registry.svc:5000/test/mcp-tools-server:latest
          ports:
            - containerPort: 8080
          env:
            - name: OPENWEATHER_API_KEY
              valueFrom:
                secretKeyRef:
                  name: mcp-secrets
                  key: openweather-api-key
          envFrom:
            - configMapRef:
                name: mcp-config
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          # ★ /health 없으므로 tcpSocket 사용
          readinessProbe:
            tcpSocket:
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 10
          livenessProbe:
            tcpSocket:
              port: 8080
            initialDelaySeconds: 20
            periodSeconds: 30
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-tools-server
  namespace: test
spec:
  selector:
    app: mcp-tools-server
  ports:
    - port: 8080
      targetPort: 8080
---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: mcp-tools-server
  namespace: test
spec:
  to:
    kind: Service
    name: mcp-tools-server
  port:
    targetPort: 8080
```

### 2-7. MCP Agent Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-agent
  namespace: test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-agent
  template:
    metadata:
      labels:
        app: mcp-agent
      annotations:
        sidecar.istio.io/inject: "false"   # ★ Istio mTLS 비활성화
    spec:
      containers:
        - name: mcp-agent
          image: image-registry.openshift-image-registry.svc:5000/test/mcp-agent:latest
          command: ["sleep", "infinity"]   # ★ oc exec으로 직접 실행
          stdin: true
          tty: true
          env:
            - name: OLLAMA_BASE_URL
              value: "http://mcp-llm-service.test.svc.cluster.local:11434/v1"
            - name: LLM_MODEL
              value: "gemma4:26b"
            - name: MCP_SERVER_URL
              value: "http://mcp-tools-server.test.svc.cluster.local:8080"
            - name: TRANSPORT
              value: "http"
            - name: OLLAMA_API_KEY
              value: "ollama"
          envFrom:
            - configMapRef:
                name: mcp-config
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
```

### 2-8. Secret (API 키)
```bash
# 생성 명령
oc create secret generic mcp-secrets \
  --from-literal=openweather-api-key="<YOUR_KEY>" \
  -n test
```

---

## 3. 이미지 빌드 및 배포 순서

```bash
# 1. OpenShift 내부 레지스트리 로그인
REGISTRY=$(oc get route default-route -n openshift-image-registry \
  --template='{{ .spec.host }}')
podman login -u $(oc whoami) -p $(oc whoami -t) $REGISTRY --tls-verify=false

# 2. 이미지 빌드 & Push (또는 oc new-build 방식)
oc new-build --name=mcp-tools-server --binary=true --strategy=docker -n test
oc start-build mcp-tools-server --from-dir=. --follow -n test

oc new-build --name=mcp-agent --binary=true --strategy=docker -n test
oc start-build mcp-agent --from-dir=. --follow -n test

# 3. Secret 생성
oc create secret generic mcp-secrets \
  --from-literal=openweather-api-key="<KEY>" -n test

# 4. ConfigMap 적용
oc apply -f configmap.yaml

# 5. Ollama SA 권한 부여 (한 번만)
oc create sa mcp-server-sa -n test
oc adm policy add-scc-to-user anyuid -z mcp-server-sa -n test

# 6. 리소스 배포
oc apply -f deploy/openshift/ollama-test-deployment.yaml
oc apply -f deploy/openshift/mcp-server-deployment.yaml
oc apply -f deploy/openshift/agent-deployment.yaml

# 7. 에이전트 실행
oc exec -it deployment/mcp-agent -n test -- python client/agent.py
```

# MCP 서버 OpenShift 구축 가이드 (Part 2: 트러블슈팅 & 아키텍처)

## 1. 발생했던 문제와 해결 방법 전체 정리

---

### 🔴 문제 1: PodSecurity 위반 (Ollama runAsUser=0)

**증상**
```
Warning: would violate PodSecurity "restricted:latest":
  runAsUser=0 (pod must not set runAsUser=0)
  allowPrivilegeEscalation != false
  unrestricted capabilities
  seccompProfile not set
Deployment created → but 0/1 READY (pod never starts)
```

**원인**  
OpenShift의 `restricted` SCC(Security Context Constraint)는 기본적으로 root 실행을 금지합니다.  
Ollama 컨테이너는 내부적으로 root(UID 0)로 실행해야 GPU 드라이버와 모델 파일에 접근할 수 있습니다.

**해결**
```bash
# 1. 전용 ServiceAccount 생성
oc create sa mcp-server-sa -n test

# 2. anyuid SCC 부여 (root 포함 모든 UID 허용)
oc adm policy add-scc-to-user anyuid -z mcp-server-sa -n test

# 3. Deployment에 SA 지정
# spec.template.spec.serviceAccountName: mcp-server-sa
# spec.template.spec.securityContext.runAsUser: 0
```

> **핵심 개념**: OpenShift SCC는 Kubernetes의 PodSecurityPolicy 역할을 합니다.  
> `anyuid` = "any user ID"로 실행 허용. `privileged` SCC보다 덜 위험하지만 root는 허용됩니다.

---

### 🔴 문제 2: 421 Misdirected Request (Istio mTLS 충돌)

**증상**
```
mcp-agent → mcp-tools-server POST /messages
→ HTTP 421 Misdirected Request
```

**원인**  
네임스페이스에 Istio/OSSM(OpenShift Service Mesh)이 활성화된 경우,  
사이드카 프록시가 HTTP 요청을 mTLS로 가로채면서 일반 HTTP 연결을 거부합니다.  
MCP의 SSE(Server-Sent Events) 연결은 특히 Istio와 충돌이 심합니다.

**해결**  
Pod 레벨에서 Istio 사이드카 주입을 비활성화:
```yaml
metadata:
  annotations:
    sidecar.istio.io/inject: "false"   # ← 이 한 줄로 해결
```

> **주의**: 네임스페이스 전체에 Istio가 있어도 Pod 단위로 제외 가능합니다.

---

### 🔴 문제 3: MCP SSE DNS Rebinding Protection (Host 헤더 검증 실패)

**증상**
```
mcp-agent가 http://mcp-tools-server.test.svc.cluster.local:8080/sse 접속 시
→ 연결 즉시 끊김 또는 403
```

**원인**  
`mcp` Python 라이브러리의 SSE 서버는 기본적으로 **DNS Rebinding Protection**을 적용합니다.  
`Host` 헤더가 `127.0.0.1` 또는 `localhost`가 아니면 요청을 거부합니다.  
클러스터 내부 DNS(`mcp-tools-server.test.svc.cluster.local`)는 이 검증을 통과하지 못합니다.

**해결**  
`SseServerTransport`를 직접 생성해서 보안 설정을 비활성화:
```python
from mcp.server.sse import SseServerTransport

sse_transport = SseServerTransport(
    endpoint="/messages",
    security_settings=None,   # ← DNS rebinding protection 완전 비활성화
)
```
그리고 `uvicorn`에 proxy 헤더 허용 설정 추가:
```python
uvicorn.run(
    starlette_app,
    host="0.0.0.0",
    forwarded_allow_ips="*",   # ← 모든 IP의 X-Forwarded-For 허용
    proxy_headers=True,
)
```

---

### 🔴 문제 4: ConfigMap OLLAMA_BASE_URL이 잘못된 네임스페이스 지정

**증상**
```
mcp-agent → Ollama 연결 시
openai.APIConnectionError: Connection error.
```

**원인**  
ConfigMap의 `OLLAMA_BASE_URL`이 `multi-agent` 네임스페이스의 서비스를 가리키고 있었습니다:
```
http://service-gemma4.multi-agent.svc.cluster.local:11434/v1  ← 잘못됨
```

**해결**  
같은 `test` 네임스페이스의 서비스로 수정:
```bash
oc patch configmap mcp-config -n test --type merge -p \
  '{"data":{"OLLAMA_BASE_URL":"http://mcp-llm-service.test.svc.cluster.local:11434/v1"}}'
```
그리고 Deployment 환경변수도 직접 주입:
```bash
oc set env deployment/mcp-agent -n test \
  OLLAMA_BASE_URL="http://mcp-llm-service.test.svc.cluster.local:11434/v1" \
  LLM_MODEL="gemma4:26b" \
  TRANSPORT="http"
```

> **규칙**: 같은 네임스페이스 서비스는 `서비스명:포트`만으로도 됩니다.  
> 다른 네임스페이스는 반드시 `서비스명.네임스페이스.svc.cluster.local:포트` 사용.

---

### 🔴 문제 5: Ollama Service가 없어서 Endpoints 없음

**증상**
```
oc get endpoints -n test
NAME               ENDPOINTS
mcp-llm-service    <none>   ← Endpoints가 없음
```

**원인**  
`mcp-llm-gemma4` Deployment는 만들었지만, **Service 리소스를 생성하지 않았습니다.**  
Kubernetes에서 Pod는 Service 없이는 다른 Pod에서 접근할 수 없습니다.

**해결**
```bash
cat <<EOF | oc apply -f -
apiVersion: v1
kind: Service
metadata:
  name: mcp-llm-service
  namespace: test
spec:
  selector:
    app: mcp-llm      # ← Pod의 label과 반드시 일치해야 함
  ports:
    - port: 11434
      targetPort: 11434
  type: ClusterIP
EOF
```

---

### 🔴 문제 6: Liveness/Readiness Probe가 /health 404

**증상**
```
Liveness probe failed: HTTP probe failed with statuscode: 404
Pod가 계속 재시작됨 (CrashLoopBackOff)
```

**원인**  
MCP 서버 YAML에 `path: /health` probe가 설정되어 있었지만,  
실제 서버는 `/health` 엔드포인트를 구현하지 않았습니다.  
(실제 엔드포인트는 `/sse`, `/messages`만 존재)

**해결**  
HTTP probe 대신 **tcpSocket probe** 사용 (포트만 열려있으면 통과):
```yaml
readinessProbe:
  tcpSocket:
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 10
livenessProbe:
  tcpSocket:
    port: 8080
  initialDelaySeconds: 20
  periodSeconds: 30
```

---

### 🔴 문제 7: NFS PVC MountVolume 실패

**증상**
```
Warning FailedMount: MountVolume.SetUp failed for volume "master2-100g-pv2"
mount.nfs: Connection refused
NFS 서버: 10.7.21.203:/var/export/llms
```

**원인**  
이전 Pod가 PVC를 잡고 있는 상태에서 강제 종료 후 새 Pod가 뜰 때,  
NFS 서버의 이전 mount lock이 해제되지 않아 새 마운트가 실패했습니다.  
`RWX`(ReadWriteMany) PVC는 여러 Pod가 동시 마운트 가능하지만,  
NFS lock 문제가 생기면 복구에 시간이 필요합니다.

**해결**  
- 시간이 지나면 자동 복구됨 (NFS lock timeout 대기)
- 필요시 NFS 서버(10.7.21.203)에서 exportfs -r 또는 서비스 재시작

---

### 🔴 문제 8: mcp-agent가 대화형 CLI라 로그가 안 보임

**증상**
```
oc logs deployment/mcp-agent -n test --tail=30
→ (출력 없음)
```

**원인**  
`agent.py`는 `input()`으로 사용자 입력을 기다리는 대화형 프로그램입니다.  
아무 입력이 없으면 프로세스는 대기 중이라 로그가 없습니다.

**해결**  
Deployment의 기본 command를 `sleep infinity`로 바꾸고, `oc exec`으로 직접 실행:
```bash
# 에이전트 직접 실행
oc exec -it deployment/mcp-agent -n test -- python client/agent.py

# 자동 입력 테스트
printf "안녕?\n종료\n" | oc exec -i deployment/mcp-agent -n test -- python client/agent.py
```

---

## 2. OpenShift 배포 시 주의사항 체크리스트

```
[ ] SCC: GPU/root 필요 Pod는 anyuid SCC + 전용 SA 사용
[ ] Istio: sidecar.istio.io/inject: "false" 어노테이션 필수
[ ] DNS: 내부 서비스는 <name>.<namespace>.svc.cluster.local:port 형식
[ ] Service: Pod만 만들면 안 됨, 반드시 Service 리소스도 생성
[ ] Probe: 서버에 /health 없으면 tcpSocket probe 사용
[ ] Secret: API 키는 반드시 Secret으로 관리, env에 직접 쓰지 말 것
[ ] GPU: nvidia.com/gpu: "1" 리소스 요청 + toleration 설정
[ ] PVC: NFS 기반 PVC는 Pod 재시작 시 mount lock 문제 주의
[ ] 이미지: OpenShift 내부 레지스트리 사용 시 BuildConfig 방식 권장
[ ] OLLAMA_HOST: 반드시 0.0.0.0 (기본값 127.0.0.1이면 다른 Pod 접근 불가)
```

---

## 3. MCP 아키텍처 상세 설명

### 3-1. MCP란?

**Model Context Protocol** - Anthropic이 만든 개방형 표준.  
LLM이 외부 도구(Tool), 데이터, 서비스와 소통하는 방법을 표준화합니다.

```
핵심 아이디어:
  LLM은 "어떤 도구를 쓸지" 결정 → MCP 서버가 실제로 실행
  결과를 다시 LLM에게 전달 → LLM이 자연어로 답변
```

### 3-2. 전체 데이터 흐름

```
사용자: "서울 날씨 알려줘"
    │
    ▼
[mcp-agent] ── OpenAI 호환 API ──▶ [Ollama + gemma4:26b]
    │                                       │
    │                              LLM이 판단:
    │                              "weather Tool 필요"
    │                              tool_calls: [{name:"weather", args:{city:"Seoul"}}]
    │                                       │
    ◀──────────────────────────────────────┘
    │
    │ MCP Protocol (JSON-RPC 2.0 over SSE)
    ▼
[mcp-tools-server]
    │  weather("Seoul") 실행
    │  → OpenWeatherMap API 호출
    │  → 결과: {temp: 19.76, ...}
    │
    ▼
[mcp-agent]
    │  결과를 LLM에게 전달
    ▼
[Ollama + gemma4:26b]
    │  자연어 답변 생성
    ▼
사용자: "현재 서울은 맑음, 19.76°C입니다..."
```

### 3-3. MCP Transport 방식 비교

| 방식 | 사용 환경 | 장단점 |
|------|-----------|--------|
| **stdio** | 로컬 개발 (Claude Desktop 등) | 간단, 네트워크 불필요, 원격 불가 |
| **SSE (HTTP)** | OpenShift/K8s 배포 | 원격 가능, Istio 충돌 주의 |
| **Streamable HTTP** | 최신 MCP 표준 | SSE보다 안정적, 라이브러리 지원 필요 |

> 이번 구축에서는 **SSE (Server-Sent Events)** 방식 사용

### 3-4. SSE Transport 통신 순서

```
1. mcp-agent → GET /sse (SSE 연결 수립, 지속 연결)
   ← event: endpoint\ndata: /messages?session_id=abc123

2. mcp-agent → POST /messages?session_id=abc123
   Body: {"method": "initialize", ...}
   ← 202 Accepted (SSE 채널로 응답 옴)

3. mcp-agent → POST /messages?session_id=abc123
   Body: {"method": "tools/list", ...}
   ← SSE 이벤트로 Tool 목록 수신

4. (LLM이 Tool 호출 결정 후)
   mcp-agent → POST /messages?session_id=abc123
   Body: {"method": "tools/call", "params": {"name": "weather", "arguments": {...}}}
   ← SSE 이벤트로 실행 결과 수신
```

### 3-5. server.py 핵심 구조

```python
from mcp.server.fastmcp import FastMCP

# 1. 서버 초기화
mcp = FastMCP(name="mcp-tools-server", host="0.0.0.0", port=8080)

# 2. Tool 등록 (데코레이터 방식)
@mcp.tool()
def weather(city: str, units: str = "metric") -> str:
    """도구 설명 (LLM이 이 docstring으로 언제 쓸지 판단)"""
    return get_weather(city, units)

# 3. SSE 서버 시작 (Starlette + uvicorn)
sse_transport = SseServerTransport(endpoint="/messages", security_settings=None)

starlette_app = Starlette(routes=[
    Route("/sse", endpoint=handle_sse),          # GET: SSE 연결
    Mount("/messages", app=sse_transport.handle_post_message),  # POST: 메시지
])

uvicorn.run(starlette_app, host="0.0.0.0", port=8080,
            forwarded_allow_ips="*", proxy_headers=True)
```

### 3-6. agent.py 핵심 구조

```python
from mcp.client.sse import sse_client
from mcp import ClientSession
from openai import AsyncOpenAI

# 1. MCP 서버에 SSE 연결
async with sse_client("http://mcp-tools-server:8080/sse") as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()

        # 2. Tool 목록 가져오기
        tools_response = await session.list_tools()

        # 3. MCP Tool → OpenAI Tool 포맷 변환
        openai_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            }
        } for tool in tools_response.tools]

        # 4. LLM 호출 (Ollama OpenAI 호환 API)
        llm = AsyncOpenAI(base_url="http://mcp-llm-service:11434/v1", api_key="ollama")
        response = await llm.chat.completions.create(
            model="gemma4:26b",
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
        )

        # 5. Tool Call 감지 → MCP 서버에 실행 요청
        if response.choices[0].message.tool_calls:
            for tc in response.choices[0].message.tool_calls:
                result = await session.call_tool(tc.function.name,
                                                  json.loads(tc.function.arguments))
```

### 3-7. 최종 완성된 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                   OpenShift Cluster                      │
│                   namespace: test                        │
│                                                         │
│  ┌──────────────────────┐                               │
│  │   mcp-agent Pod      │                               │
│  │   python:3.11        │                               │
│  │   cmd: sleep ∞       │◄─── oc exec -it ... ──────── │◄── 사용자
│  │   TRANSPORT=http     │                               │
│  └──────────┬───────────┘                               │
│             │ SSE (HTTP)              OpenAI API        │
│             │ /sse, /messages         /v1/chat          │
│             ▼                             ▼             │
│  ┌──────────────────────┐   ┌────────────────────────┐  │
│  │  mcp-tools-server    │   │  mcp-llm-gemma4        │  │
│  │  python:3.11         │   │  ollama/ollama:latest  │  │
│  │  FastMCP + Starlette │   │  gemma4:26b (17GB)     │  │
│  │  port: 8080          │   │  V100 32GB GPU         │  │
│  │                      │   │  port: 11434           │  │
│  │  Tools:              │   │  PVC: pvc-gemma4 (NFS) │  │
│  │  - calculator        │   └────────────────────────┘  │
│  │  - get_datetime      │     mcp-llm-service:11434     │
│  │  - weather           │                               │
│  │  - find_city ...     │                               │
│  └──────────┬───────────┘                               │
│    Service: │ mcp-tools-server:8080                     │
│    Route: mcp-tools-server-test.apps.ocp.virt.local     │
│             │                                           │
│             ▼ 외부 API 호출                              │
└─────────────────────────────────────────────────────────┘
             │
             ▼
   OpenWeatherMap API (인터넷)
   NTP pool.ntp.org (인터넷)
```

---

## 4. 혼자 처음부터 구축할 때 순서

```
1. Python 코드 작성
   └─ server/server.py  : FastMCP + @mcp.tool() 데코레이터로 Tool 등록
   └─ client/agent.py   : sse_client + OpenAI SDK로 LLM-Tool 루프 구현

2. Dockerfile 작성
   └─ 서버용: CMD python server/server.py --transport http
   └─ 에이전트용: CMD sleep infinity

3. OpenShift에 이미지 빌드
   └─ oc new-build + oc start-build (Binary 빌드)

4. 권한 설정
   └─ SA 생성 + anyuid SCC 부여 (Ollama에만 필요)

5. Secret / ConfigMap 생성
   └─ API 키는 Secret
   └─ 서비스 URL은 ConfigMap

6. Deployment 배포
   └─ Ollama → MCP Server → Agent 순서로 배포

7. 연결 확인
   └─ oc get endpoints
   └─ curl -N http://<route>/sse
   └─ oc exec -it agent -- python client/agent.py
```

