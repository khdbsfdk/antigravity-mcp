#!/bin/bash
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig
NS=test

echo "=== [1] 전체 Pod/SVC 상태 ==="
oc get pods -n $NS
echo ""
oc get svc -n $NS

echo ""
echo "=== [2] mcp-tools-server 헬스체크 (Route 경유) ==="
curl -s --max-time 5 http://mcp-tools-server-test.apps.ocp.virt.local/health && echo "" || echo "FAIL"

echo ""
echo "=== [3] mcp-agent Pod에서 → MCP server 연결 ==="
oc exec deployment/mcp-agent -n $NS -- python3 << 'PYEOF'
import urllib.request
try:
    r = urllib.request.urlopen('http://mcp-tools-server.test.svc.cluster.local:8080/health', timeout=5)
    print('MCP /health OK:', r.read().decode())
except Exception as e:
    print('MCP /health FAIL:', e)

try:
    r = urllib.request.urlopen('http://mcp-tools-server.test.svc.cluster.local:8080/sse', timeout=3)
    print('MCP /sse OK status:', r.status)
except Exception as e:
    print('MCP /sse result:', str(e)[:100])
PYEOF

echo ""
echo "=== [4] mcp-agent Pod에서 → Ollama 연결 ==="
oc exec deployment/mcp-agent -n $NS -- python3 << 'PYEOF'
import urllib.request, json
try:
    r = urllib.request.urlopen('http://mcp-llm-service.test.svc.cluster.local:11434/api/version', timeout=5)
    print('Ollama version OK:', r.read().decode())
except Exception as e:
    print('Ollama version FAIL:', e)

try:
    r = urllib.request.urlopen('http://mcp-llm-service.test.svc.cluster.local:11434/api/tags', timeout=5)
    data = json.loads(r.read().decode())
    models = [m['name'] for m in data.get('models', [])]
    print('Ollama models:', models)
except Exception as e:
    print('Ollama tags FAIL:', e)
PYEOF

echo ""
echo "=== [5] mcp-agent 환경변수 최종 확인 ==="
oc set env deployment/mcp-agent -n $NS --list

echo ""
echo "=== [6] mcp-tools-server 로그 (최근 20줄) ==="
oc logs deployment/mcp-tools-server -n $NS --tail=20

echo ""
echo "========================================="
echo " 연결 점검 완료"
echo "========================================="
