#!/bin/bash
# mcp-agent 실제 실행 테스트 (non-interactive - 단일 질문)
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig
NS=test

echo "========================================="
echo " MCP Agent 실행 테스트 (자동 입력)"
echo "========================================="

echo ""
echo "=== Ollama 모델 프리로드 테스트 (120초 타임아웃) ==="
echo "  gemma4:26b 모델 첫 로딩에 시간이 걸릴 수 있습니다..."
timeout 120 oc exec deployment/mcp-agent -n $NS -- python -c "
import urllib.request, json, time

url_tags = 'http://mcp-llm-service.test.svc.cluster.local:11434/api/tags'
url_chat = 'http://mcp-llm-service.test.svc.cluster.local:11434/v1/chat/completions'

# 모델 목록 확인
try:
    r = urllib.request.urlopen(url_tags, timeout=30)
    data = json.loads(r.read().decode())
    models = [m['name'] for m in data.get('models', [])]
    print('[OK] Ollama models:', models)
except Exception as e:
    print('[FAIL] models:', e)

# LLM 단순 테스트
print('[TEST] LLM 추론 시작 (첫 로딩 최대 2분 소요)...')
payload = json.dumps({
    'model': 'gemma4:26b',
    'messages': [{'role': 'user', 'content': '안녕하세요. 한 문장으로 답해주세요.'}],
    'stream': False,
    'max_tokens': 30
}).encode()
req = urllib.request.Request(url_chat, data=payload, headers={'Content-Type': 'application/json'})
try:
    r = urllib.request.urlopen(req, timeout=110)
    data = json.loads(r.read().decode())
    content = data['choices'][0]['message']['content']
    print('[OK] LLM 응답:', content)
except Exception as e:
    print('[FAIL] LLM:', e)
" 2>&1 || echo "[ERROR] 타임아웃 (120초 초과)"

echo ""
echo "=== MCP Agent 실행 (echo 입력으로 자동 테스트) ==="
echo "  '1+1은 뭐야?' 질문을 자동으로 입력합니다..."
echo "1+1은 뭐야?
종료" | timeout 120 oc exec -i deployment/mcp-agent -n $NS -- python client/agent.py 2>&1 || echo "[INFO] 에이전트 종료"

echo ""
echo "========================================="
echo " 테스트 완료"
echo "========================================="
