#!/bin/bash
# ============================================================
# MCP 서버 완전 복원 스크립트
# bastion 서버에서 실행
# ============================================================
set -e
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig

NS=test
echo "=========================================="
echo " MCP 서버 복원 시작 (namespace: $NS)"
echo "=========================================="

# [1] BC dockerfilePath 수정
echo ""
echo "=== [1] BuildConfig dockerfilePath 설정 ==="
oc patch bc mcp-tools-server -n $NS --type merge -p '{"spec":{"strategy":{"dockerStrategy":{"dockerfilePath":"deploy/Dockerfile"}}}}'
echo "mcp-tools-server BC → deploy/Dockerfile"

oc patch bc mcp-agent -n $NS --type merge -p '{"spec":{"strategy":{"dockerStrategy":{"dockerfilePath":"deploy/Dockerfile.client"}}}}'
echo "mcp-agent BC → deploy/Dockerfile.client"

# [2] mcp-tools-server 이미지 빌드
echo ""
echo "=== [2] mcp-tools-server 이미지 빌드 ==="
cd /home/antigravity/mcp_test
oc start-build mcp-tools-server --from-dir=. -n $NS --follow

# [3] mcp-agent 이미지 빌드
echo ""
echo "=== [3] mcp-agent 이미지 빌드 ==="
oc start-build mcp-agent --from-dir=. -n $NS --follow

# [4] Deployment 롤아웃 (이미지 갱신)
echo ""
echo "=== [4] Deployment 재시작 ==="
oc rollout restart deployment/mcp-tools-server -n $NS 2>/dev/null || true
oc rollout restart deployment/mcp-agent -n $NS 2>/dev/null || true

# [5] 롤아웃 완료 대기
echo ""
echo "=== [5] 롤아웃 완료 대기 ==="
oc rollout status deployment/mcp-tools-server -n $NS --timeout=120s 2>&1 || true
oc rollout status deployment/mcp-agent -n $NS --timeout=60s 2>&1 || true

# [6] 최종 상태 확인
echo ""
echo "=== [6] 최종 Pod 상태 ==="
oc get pods -n $NS
echo ""
echo "=== Deployment 상태 ==="
oc get deployment -n $NS
echo ""
echo "=== Service 상태 ==="
oc get svc -n $NS
echo ""
echo "=========================================="
echo " 복원 완료!"
echo "=========================================="
