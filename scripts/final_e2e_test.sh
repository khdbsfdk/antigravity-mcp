#!/bin/bash
# MCP Agent E2E 최종 테스트
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig
NS=test

echo "========================================="
echo " MCP Agent E2E 최종 테스트"
echo "========================================="
echo ""

echo "=== [1] 모든 Pod 상태 ==="
oc get pods -n $NS | grep -E "mcp|NAME"

echo ""
echo "=== [2] Ollama 모델 확인 ==="
oc exec deployment/mcp-llm-gemma4 -n $NS -- ollama list 2>&1

echo ""
echo "=== [3] mcp-agent에서 Ollama 직접 호출 테스트 ==="
oc exec deployment/mcp-agent -n $NS -- python -c "
import urllib.request, json
url = 'http://mcp-llm-service.test.svc.cluster.local:11434/api/version'
try:
    r = urllib.request.urlopen(url, timeout=10)
    print('[OK] Ollama version:', r.read().decode().strip())
except Exception as e:
    print('[FAIL]', e)
" 2>&1

echo ""
echo "=== [4] MCP Agent 실행 - 자동 질문 입력 ==="
echo "  질문: 지금 서울 날씨 어때? / 1234 * 5678 계산해줘 / 종료"
printf "지금 서울 날씨 어때?\n1234 * 5678 계산해줘\n종료\n" | \
  timeout 180 oc exec -i deployment/mcp-agent -n $NS -- python client/agent.py 2>&1

echo ""
echo "========================================="
echo " 테스트 완료"
echo "========================================="
