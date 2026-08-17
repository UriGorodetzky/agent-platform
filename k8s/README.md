# Kubernetes manifests

Run the platform on a local cluster (Docker Desktop Kubernetes). Images are
built locally and shared with the cluster — no registry push needed.

```bash
kubectl apply -f k8s/echo-agent.yaml       # Deployment (3 replicas) + Service
kubectl apply -f k8s/orchestrator.yaml     # ConfigMap + Deployment + Service
```

Reach the orchestrator (NodePort isn't auto-mapped on the kind-based cluster):

```bash
kubectl port-forward service/orchestrator 8080:8000
curl http://localhost:8080/health
```

## Autoscaling (HPA)

The HPA needs a metrics source. Install metrics-server once (the extra flag is
required on Docker Desktop's kind-based cluster):

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl patch deployment metrics-server -n kube-system --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
```

Then:

```bash
kubectl apply -f k8s/echo-agent-hpa.yaml   # scale 3..10 pods at 50% CPU
kubectl get hpa echo-agent -w              # watch it react to load
```

## Clean up

```bash
kubectl delete -f k8s/
```
