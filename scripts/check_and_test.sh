#!/bin/bash
# MCP + Ollama 연결 상태 종합 점검 스크립트
set -e
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig
NS=test

echo "========================================"
echo " MCP + Ollama 연결 상태 점검"
echo "========================================"

echo ""
echo "=== [1] 전체 Pod 상태 ==="
oc get pods -n $NS

echo ""
echo "=== [2] Service 목록 ==="
oc get svc -n $NS

echo ""
echo "=== [3] mcp-tools-server 로그 (최근 30줄) ==="
oc logs deployment/mcp-tools-server -n $NS --tail=30 2>&1

echo ""
echo "=== [4] mcp-agent 로그 (최근 30줄) ==="
oc logs deployment/mcp-agent -n $NS --tail=30 2>&1

echo ""
echo "=== [5] mcp-agent 환경변수 ==="
oc set env deployment/mcp-agent -n $NS --list 2>&1

echo ""
echo "=== [6] MCP Server health 체크 (Ollama Pod에서) ==="
oc exec deployment/mcp-llm-gemma4 -n $NS -- \
  python3 -c "
import urllib.request, json
try:
    r = urllib.request.urlopen('http://mcp-tools-server.test.svc.cluster.local:8080/health', timeout=5)
    print('health OK:', r.read().decode())
except Exception as e:
    print('health FAIL:', e)
" 2>&1

echo ""
echo "=== [7] MCP Server SSE 엔드포인트 체크 ==="
oc exec deployment/mcp-llm-gemma4 -n $NS -- \
  python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('http://mcp-tools-server.test.svc.cluster.local:8080/sse', timeout=3)
    print('SSE OK:', r.status)
except Exception as e:
    print('SSE result:', e)
" 2>&1

echo ""
echo "=== [8] Ollama API 체크 (내부) ==="
oc exec deployment/mcp-llm-gemma4 -n $NS -- \
  python3 -c "
import urllib.request, json
try:
    r = urllib.request.urlopen('http://localhost:11434/api/tags', timeout=5)
    data = json.loads(r.read().decode())
    models = [m['name'] for m in data.get('models', [])]
    print('Ollama models:', models)
except Exception as e:
    print('Ollama FAIL:', e)
" 2>&1

echo ""
echo "=== [9] Ollama API 체크 (서비스명으로) ==="
oc exec deployment/mcp-agent -n $NS -- \
  python3 -c "
import urllib.request, json
try:
    r = urllib.request.urlopen('http://mcp-llm-service.test.svc.cluster.local:11434/api/version', timeout=5)
    print('Ollama via service OK:', r.read().decode())
except Exception as e:
    print('Ollama via service FAIL:', e)
" 2>&1

echo ""
echo "=== [10] MCP Server /mcp 엔드포인트 체크 ==="
oc exec deployment/mcp-llm-gemma4 -n $NS -- \
  python3 -c "
import urllib.request
try:
    req = urllib.request.Request(
        'http://mcp-tools-server.test.svc.cluster.local:8080/mcp',
        data=b'{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}',
        headers={'Content-Type': 'application/json'}
    )
    r = urllib.request.urlopen(req, timeout=5)
    print('MCP /mcp OK:', r.read().decode()[:200])
except Exception as e:
    print('MCP /mcp result:', e)
" 2>&1

echo ""
echo "========================================"
echo " 점검 완료"
echo "========================================"
