# Phase 68: Kubernetes Manifests

> **Status**: Future
>
> **Prerequisites**: Phase 67 (moved2 Backend) complete
>
> **Part of**: Cloud-Native Demo Initiative

## Overview

Create production-ready Kubernetes manifests for deploying JoustMania with the moved2 architecture. This enables proper cloud-native deployment with hardware abstraction at the edge.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Kubernetes Cluster                           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    joustmania namespace                   │   │
│  │                                                          │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │   │
│  │  │ Redis   │ │Settings │ │ Menu    │ │ WebUI   │       │   │
│  │  │         │ │ Service │ │ Service │ │         │       │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘       │   │
│  │       │           │           │           │             │   │
│  │       └───────────┴─────┬─────┴───────────┘             │   │
│  │                         │                                │   │
│  │                  ┌──────▼──────┐                         │   │
│  │                  │    Game     │                         │   │
│  │                  │ Coordinator │                         │   │
│  │                  └──────┬──────┘                         │   │
│  │                         │ gRPC                           │   │
│  │                  ┌──────▼──────┐                         │   │
│  │                  │ Controller  │                         │   │
│  │                  │  Manager    │  ◄── CONTROLLER_BACKEND │   │
│  │                  │ (moved2)    │      =moved2            │   │
│  │                  └──────┬──────┘                         │   │
│  │                         │ UDP :17778                     │   │
│  └─────────────────────────┼────────────────────────────────┘   │
│                            │                                     │
│  ┌─────────────────────────▼────────────────────────────────┐   │
│  │              Edge Node (bluetooth: "true")                │   │
│  │                                                           │   │
│  │  ┌───────────────────────────────────────────────────┐   │   │
│  │  │ DaemonSet: moved2-daemon                          │   │   │
│  │  │                                                    │   │   │
│  │  │  - hostNetwork: true                               │   │   │
│  │  │  - Runs psmoveapi moved2                           │   │   │
│  │  │  - Exposes UDP :17778                              │   │   │
│  │  └───────────────────────────────────────────────────┘   │   │
│  │                         │                                 │   │
│  │                  ┌──────▼──────┐                          │   │
│  │                  │  Bluetooth  │                          │   │
│  │                  │  Hardware   │                          │   │
│  │                  └─────────────┘                          │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
k8s/
├── base/
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── redis/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── settings/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── configmap.yaml
│   ├── controller-manager/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── game-coordinator/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── menu/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── webui/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── ingress.yaml
│   ├── audio/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   └── moved2-daemon/
│       └── daemonset.yaml
├── overlays/
│   ├── development/
│   │   ├── kustomization.yaml
│   │   └── patches/
│   ├── production/
│   │   ├── kustomization.yaml
│   │   └── patches/
│   └── demo/
│       ├── kustomization.yaml
│       └── patches/
└── helm/
    └── joustmania/
        ├── Chart.yaml
        ├── values.yaml
        └── templates/
```

## Key Manifests

### Namespace

```yaml
# k8s/base/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: joustmania
  labels:
    app.kubernetes.io/name: joustmania
    app.kubernetes.io/part-of: joustmania
```

### moved2 DaemonSet (Edge)

```yaml
# k8s/base/moved2-daemon/daemonset.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: moved2-daemon
  namespace: joustmania
  labels:
    app: moved2-daemon
spec:
  selector:
    matchLabels:
      app: moved2-daemon
  template:
    metadata:
      labels:
        app: moved2-daemon
    spec:
      # Only on nodes with Bluetooth hardware
      nodeSelector:
        joustmania.io/bluetooth: "true"

      # Required for Bluetooth adapter access
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet

      tolerations:
      - key: "joustmania.io/edge"
        operator: "Exists"
        effect: "NoSchedule"

      containers:
      - name: moved2
        image: joustmania/moved2-daemon:latest
        command: ["/app/entrypoint.sh"]

        securityContext:
          capabilities:
            add:
            - NET_ADMIN
            - NET_RAW

        ports:
        - containerPort: 17778
          protocol: UDP
          hostPort: 17778

        resources:
          limits:
            memory: 128Mi
          requests:
            memory: 64Mi

        livenessProbe:
          exec:
            command: ["psmove", "list"]
          initialDelaySeconds: 30
          periodSeconds: 30

        lifecycle:
          preStop:
            exec:
              command: ["/app/cleanup.sh"]

      terminationGracePeriodSeconds: 10
```

### Controller Manager Deployment

```yaml
# k8s/base/controller-manager/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: controller-manager
  namespace: joustmania
spec:
  replicas: 1
  selector:
    matchLabels:
      app: controller-manager
  template:
    metadata:
      labels:
        app: controller-manager
    spec:
      containers:
      - name: controller-manager
        image: joustmania/controller-manager:latest

        env:
        - name: CONTROLLER_BACKEND
          value: "moved2"
        - name: MOVED2_HOST
          value: "moved2-daemon.joustmania.svc.cluster.local"
        - name: MOVED2_PORT
          value: "17778"
        - name: OTEL_SERVICE_NAME
          value: "controller-manager"
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: "http://otel-collector:4317"

        ports:
        - containerPort: 50052
          name: grpc

        resources:
          limits:
            memory: 256Mi
          requests:
            memory: 128Mi

        livenessProbe:
          grpc:
            port: 50052
          initialDelaySeconds: 10
          periodSeconds: 10

        readinessProbe:
          grpc:
            port: 50052
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Controller Manager Service

```yaml
# k8s/base/controller-manager/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: controller-manager
  namespace: joustmania
spec:
  selector:
    app: controller-manager
  ports:
  - port: 50052
    targetPort: 50052
    name: grpc
```

### WebUI Ingress

```yaml
# k8s/base/webui/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: joustmania-webui
  namespace: joustmania
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
  - host: joustmania.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: webui
            port:
              number: 80
```

### Kustomization Base

```yaml
# k8s/base/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: joustmania

resources:
- namespace.yaml
- redis/
- settings/
- controller-manager/
- game-coordinator/
- menu/
- webui/
- audio/
- moved2-daemon/

commonLabels:
  app.kubernetes.io/part-of: joustmania

images:
- name: joustmania/controller-manager
  newTag: latest
- name: joustmania/game-coordinator
  newTag: latest
- name: joustmania/settings
  newTag: latest
- name: joustmania/menu
  newTag: latest
- name: joustmania/webui
  newTag: latest
- name: joustmania/audio
  newTag: latest
- name: joustmania/moved2-daemon
  newTag: latest
```

### Production Overlay

```yaml
# k8s/overlays/production/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
- ../../base

# Production image tags
images:
- name: joustmania/controller-manager
  newTag: v1.0.0

# Production patches
patches:
- path: patches/resource-limits.yaml
- path: patches/replicas.yaml

# Production-specific config
configMapGenerator:
- name: joustmania-config
  behavior: merge
  literals:
  - LOG_LEVEL=WARNING
```

## Node Labeling

Before deploying, label edge nodes with Bluetooth hardware:

```bash
# Label nodes with Bluetooth adapters
kubectl label node rpi-node-1 joustmania.io/bluetooth=true

# Optional: Taint edge nodes
kubectl taint node rpi-node-1 joustmania.io/edge=true:NoSchedule
```

## Deployment Commands

```bash
# Development
kubectl apply -k k8s/overlays/development

# Production
kubectl apply -k k8s/overlays/production

# Check status
kubectl -n joustmania get pods
kubectl -n joustmania get services

# View logs
kubectl -n joustmania logs -f deployment/controller-manager
kubectl -n joustmania logs -f daemonset/moved2-daemon
```

## Tasks

- [ ] Create base manifests for all services
- [ ] Create moved2-daemon DaemonSet
- [ ] Create Kustomize overlays (dev, prod, demo)
- [ ] Add resource limits and requests
- [ ] Configure health checks (gRPC probes)
- [ ] Set up Ingress for WebUI
- [ ] Add NetworkPolicies for security
- [ ] Create Helm chart (optional)
- [ ] Document node labeling requirements
- [ ] Test full deployment on K3s/K8s
- [ ] Add monitoring (ServiceMonitor for Prometheus)

## Observability Integration

```yaml
# ServiceMonitor for Prometheus Operator
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: joustmania
  namespace: joustmania
spec:
  selector:
    matchLabels:
      app.kubernetes.io/part-of: joustmania
  endpoints:
  - port: metrics
    interval: 15s
```

## Cloud-Native Demo Features

This deployment showcases:

1. **Microservices**: Each component is a separate deployment
2. **Service Discovery**: Kubernetes DNS for inter-service communication
3. **Edge Computing**: moved2-daemon on edge nodes with hardware
4. **Observability**: OpenTelemetry + Prometheus + Jaeger
5. **GitOps Ready**: Kustomize overlays for environments
6. **Ingress**: External access via Ingress controller
7. **Health Checks**: Native gRPC probes
8. **Resource Management**: Limits and requests defined

## Next Steps (Beyond Phase 68)

- Service mesh integration (Istio/Linkerd)
- GitOps with Argo CD or Flux
- Horizontal Pod Autoscaler for game services
- Multi-cluster federation for large events
