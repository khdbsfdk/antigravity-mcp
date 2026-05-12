#!/bin/bash
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig

echo "=== test 네임스페이스 현재 리소스 ==="
oc project test
oc get all -n test

echo ""
echo "=== image-registry 상태 ==="
oc get pods -n openshift-image-registry

echo ""
echo "=== internal registry route ==="
oc get route default-route -n openshift-image-registry 2>/dev/null || echo "route 없음"

echo ""
echo "=== 노드 목록 ==="
oc get nodes -o wide
