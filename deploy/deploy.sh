#!/bin/bash
# ============================================================
# OpenShift 배포 자동화 스크립트
# ============================================================
# 사용법:
#   chmod +x deploy/deploy.sh
#   ./deploy/deploy.sh [namespace] [registry]
#
# 예시:
#   ./deploy/deploy.sh mcp-demo quay.io/myorg
# ============================================================

set -euo pipefail

# ─── 설정 ───────────────────────────────────────────────────
NAMESPACE="${1:-mcp-demo}"
REGISTRY="${2:-quay.io/myorg}"
IMAGE_NAME="mcp-tools-server"
IMAGE_TAG="latest"
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

echo "============================================"
echo "  MCP Tools Server - OpenShift 배포"
echo "============================================"
echo "  네임스페이스: ${NAMESPACE}"
echo "  이미지: ${FULL_IMAGE}"
echo "============================================"

# ─── 1. 네임스페이스 생성 ────────────────────────────────────
echo ""
echo "[1/5] 네임스페이스 확인/생성..."
oc get namespace "${NAMESPACE}" 2>/dev/null || oc new-project "${NAMESPACE}"
oc project "${NAMESPACE}"

# ─── 2. 이미지 빌드 및 푸시 ─────────────────────────────────
echo ""
echo "[2/5] MCP 서버 이미지 빌드..."
cd "${PROJECT_ROOT}"
docker build -f deploy/Dockerfile -t "${FULL_IMAGE}" .
echo "  ✅ 빌드 완료: ${FULL_IMAGE}"

echo ""
echo "  이미지 푸시..."
docker push "${FULL_IMAGE}"
echo "  ✅ 푸시 완료"

# ─── 3. OpenWeatherMap API 키 Secret 생성 ────────────────────
echo ""
echo "[3/5] API 키 Secret 설정..."

if [ -z "${OPENWEATHER_API_KEY:-}" ]; then
    echo "  ⚠️  OPENWEATHER_API_KEY 환경변수가 설정되지 않았습니다."
    read -p "  OpenWeatherMap API 키를 입력하세요: " OPENWEATHER_API_KEY
fi

oc create secret generic mcp-secrets \
    --from-literal=openweather-api-key="${OPENWEATHER_API_KEY}" \
    --namespace="${NAMESPACE}" \
    --dry-run=client -o yaml | oc apply -f -
echo "  ✅ Secret 생성 완료"

# ─── 4. YAML 매니페스트 적용 ─────────────────────────────────
echo ""
echo "[4/5] 매니페스트 적용..."

# 이미지 경로를 실제 경로로 치환하여 적용
sed "s|<YOUR_REGISTRY>/mcp-tools-server:latest|${FULL_IMAGE}|g" \
    "${SCRIPT_DIR}/openshift/mcp-server-deployment.yaml" | \
    sed "s|namespace: mcp-demo|namespace: ${NAMESPACE}|g" | \
    oc apply -f -

sed "s|namespace: mcp-demo|namespace: ${NAMESPACE}|g" \
    "${SCRIPT_DIR}/openshift/mcp-server-service.yaml" | \
    oc apply -f -

echo "  ✅ 매니페스트 적용 완료"

# ─── 5. 배포 상태 확인 ───────────────────────────────────────
echo ""
echo "[5/5] 배포 상태 확인..."
oc rollout status deployment/mcp-tools-server -n "${NAMESPACE}" --timeout=120s

# Route URL 출력
MCP_ROUTE=$(oc get route mcp-tools-server -n "${NAMESPACE}" -o jsonpath='{.spec.host}' 2>/dev/null || echo "Route 없음")

echo ""
echo "============================================"
echo "  ✅ 배포 완료!"
echo "  MCP 서버 URL: https://${MCP_ROUTE}"
echo ""
echo "  클라이언트에서 연결하려면:"
echo "  export OPENAI_BASE_URL=<vLLM Route URL>/v1"
echo "  export MCP_SERVER_URL=https://${MCP_ROUTE}"
echo "  python client/agent.py"
echo "============================================"
