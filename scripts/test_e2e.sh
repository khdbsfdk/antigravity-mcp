#!/bin/bash
# mcp-agent E2E 테스트 스크립트
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig
NS=test

echo "========================================="
echo " MCP Agent E2E 연결 테스트"
echo "========================================="

echo ""
echo "=== [1] mcp-agent에서 MCP 서버 /sse 연결 테스트 ==="
timeout 10 oc exec deployment/mcp-agent -n $NS -- python -c "
import urllib.request
url = 'http://mcp-tools-server.test.svc.cluster.local:8080/sse'
try:
    req = urllib.request.Request(url, headers={'Accept': 'text/event-stream'})
    r = urllib.request.urlopen(req, timeout=5)
    data = r.read(300).decode('utf-8', errors='replace')
    print('MCP /sse OK:', data[:150])
except Exception as e:
    print('MCP /sse FAIL:', e)
" 2>&1 || echo "timeout or error"

echo ""
echo "=== [2] mcp-agent에서 Ollama /api/version 테스트 ==="
oc exec deployment/mcp-agent -n $NS -- python -c "
import urllib.request, json
url = 'http://mcp-llm-service.test.svc.cluster.local:11434/api/version'
try:
    r = urllib.request.urlopen(url, timeout=5)
    print('Ollama OK:', r.read().decode())
except Exception as e:
    print('Ollama FAIL:', e)
" 2>&1

echo ""
echo "=== [3] mcp-agent에서 Ollama 모델 목록 확인 ==="
oc exec deployment/mcp-agent -n $NS -- python -c "
import urllib.request, json
url = 'http://mcp-llm-service.test.svc.cluster.local:11434/api/tags'
try:
    r = urllib.request.urlopen(url, timeout=5)
    data = json.loads(r.read().decode())
    models = [m['name'] for m in data.get('models', [])]
    print('Available models:', models)
except Exception as e:
    print('FAIL:', e)
" 2>&1

echo ""
echo "=== [4] Ollama OpenAI 호환 API 테스트 (gemma4:26b 빠른 추론) ==="
echo "  (30초 타임아웃 - 모델 첫 로딩 시 시간 소요)"
timeout 60 oc exec deployment/mcp-agent -n $NS -- python -c "
import urllib.request, json
url = 'http://mcp-llm-service.test.svc.cluster.local:11434/v1/chat/completions'
payload = json.dumps({
    'model': 'gemma4:26b',
    'messages': [{'role': 'user', 'content': '안녕! 한 문장으로 인사해줘.'}],
    'stream': False,
    'max_tokens': 50
}).encode()
req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
try:
    r = urllib.request.urlopen(req, timeout=55)
    data = json.loads(r.read().decode())
    content = data['choices'][0]['message']['content']
    print('LLM 응답:', content)
except Exception as e:
    print('LLM FAIL:', e)
" 2>&1 || echo "타임아웃 (모델 로딩 중일 수 있음)"

echo ""
echo "========================================="
echo " 테스트 완료"
echo "========================================="
