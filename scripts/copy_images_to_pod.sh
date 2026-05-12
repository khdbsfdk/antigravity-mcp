#!/bin/bash
# 이미지 파일을 MCP 서버 Pod의 /data/images/에 복사
set -e
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig
NS=test

POD=$(oc get pods -n $NS -l app=mcp-tools-server -o jsonpath='{.items[0].metadata.name}')
echo "MCP Server Pod: $POD"

# /data/images 디렉토리 생성
oc exec "$POD" -n $NS -- mkdir -p /data/images

# 이미지 복사
for f in /home/antigravity/mcp_test/image_data/*.JPG; do
    echo "Copying $(basename "$f")..."
    oc cp "$f" "$NS/$POD:/data/images/" 2>&1
done

echo ""
echo "=== Pod /data/images/ ==="
oc exec "$POD" -n $NS -- ls -la /data/images/
