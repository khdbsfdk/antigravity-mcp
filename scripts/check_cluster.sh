#!/bin/bash
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig

echo "=== BuildConfig 목록 ==="
oc get buildconfig -n multi-agent 2>/dev/null

echo ""
echo "=== ImageStream 목록 ==="
oc get imagestream -n multi-agent 2>/dev/null

echo ""
echo "=== 노드 현황 ==="
oc get nodes -o wide

echo ""
echo "=== GPU 노드 확인 ==="
oc get nodes -l nvidia.com/gpu.present=true 2>/dev/null || oc get nodes --show-labels | grep -i gpu

echo ""
echo "=== image-registry 상태 ==="
oc get pods -n openshift-image-registry

echo ""
echo "=== internal registry route ==="
oc get route -n openshift-image-registry 2>/dev/null
