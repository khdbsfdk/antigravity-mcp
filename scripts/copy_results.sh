#!/bin/bash
set -e
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig
NS=test
AGENT_POD=$(oc get pods -n $NS -l app=mcp-agent -o jsonpath='{.items[?(@.status.phase=="Running")].metadata.name}' | awk '{print $1}')
echo "Agent Pod: $AGENT_POD"

DEST=/home/antigravity/mcp_test/experiments/results
mkdir -p "$DEST"

# 실험 2 결과 복사
oc cp "$NS/$AGENT_POD:/app/experiments/results/experiment2_results.json" "$DEST/experiment2_results.json" 2>&1
oc cp "$NS/$AGENT_POD:/app/experiments/results/experiment2_report.md" "$DEST/experiment2_report.md" 2>&1

echo "=== 복사된 파일 ==="
ls -la "$DEST/"

echo ""
echo "=== 실험 2 보고서 (처음 80줄) ==="
head -80 "$DEST/experiment2_report.md"
