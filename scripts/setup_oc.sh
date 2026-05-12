#!/bin/bash
export KUBECONFIG=/home/antigravity/.kube/config/kubeconfig

echo "=== KUBECONFIG ==="
echo $KUBECONFIG

echo "=== OC Login ==="
oc login https://api.ocp.virt.local:6443 -u admin -p 'P@ssw0rd' --insecure-skip-tls-verify=true

echo "=== whoami ==="
oc whoami

echo "=== projects ==="
oc get projects

echo "=== multi-agent namespace resources ==="
oc get all -n multi-agent 2>/dev/null || echo "multi-agent namespace not found"
