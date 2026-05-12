#!/bin/bash
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig
NS=test

echo "=========================================="
echo " MCP Agent E2E 테스트"
echo "=========================================="

# 테스트 실행
printf '3 더하기 5 곱하기 2는?\n종료\n' | timeout 180 oc exec -i deployment/mcp-agent -n $NS -- python client/agent.py 2>&1

echo ""
echo "=========================================="
echo " 테스트 완료"
echo "=========================================="
