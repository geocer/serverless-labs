# MR Bot Dashboard — EKS Deployment

Solução definitiva pro problema de CORS/403 com Private API Gateway.
O Flask BFF roda **dentro da VPC** e faz proxy das chamadas pra API internamente.

```
Usuário (VPN corporativa)
        │  HTTPS (ALB interno)
        ▼
  ALB interno (dentro da VPC)
        │  ClusterIP:80
        ▼
  Pod Flask (EKS, namespace mr-dashboard)
        │  serve  GET /             → index.html
        │  proxy  GET /api/dashboard → API Gateway Private
        ▼
  API Gateway Private (5su5qmyoqc)
        │  Lambda Proxy
        ▼
  Lambda Python → DynamoDB (MergeRequestReviews)
```

**Por que funciona:** o pod tá dentro da VPC, então o Private DNS do VPCE
resolve `5su5qmyoqc.execute-api.sa-east-1.amazonaws.com` para o IP privado
automaticamente. Browser só fala com o Flask (mesmo origin), sem CORS.

---

## Pré-requisitos

- AWS CLI configurado com permissões adequadas
- Docker com BuildKit habilitado
- kubectl apontando pro seu cluster EKS
- AWS Load Balancer Controller instalado no cluster
- Certificado ACM válido pro domínio do dashboard

---

## 1. Build e Push da imagem

```bash
chmod +x build-and-push.sh

# Com tag automática (git short hash)
AWS_ACCOUNT_ID=262041882421 AWS_REGION=sa-east-1 ./build-and-push.sh

# Com tag manual
./build-and-push.sh v1.2.3
```

---

## 2. Ajustar manifests antes de aplicar

Edita `k8s/manifests.yaml` e substitui todos os `<CHANGE_ME>`:

| Campo | Onde | Valor |
|---|---|---|
| `image` | Deployment | `262041882421.dkr.ecr.sa-east-1.amazonaws.com/mr-dashboard:latest` |
| `alb.ingress.kubernetes.io/certificate-arn` | Ingress | ARN do seu certificado ACM |
| `alb.ingress.kubernetes.io/security-groups` | Ingress | SG que aceita tráfego da VPN |
| `host` | Ingress | hostname final do dashboard |
| `eks.amazonaws.com/role-arn` | ServiceAccount | IAM role se precisar de permissões adicionais |

---

## 3. Aplicar no cluster

```bash
# Primeira vez — aplica tudo
kubectl apply -f k8s/manifests.yaml

# Verificar pods
kubectl get pods -n mr-dashboard -w

# Verificar ingress (pega o DNS do ALB)
kubectl get ingress -n mr-dashboard

# Logs em tempo real
kubectl logs -f deployment/mr-dashboard -n mr-dashboard

# Testar health dentro do cluster
kubectl exec -it deployment/mr-dashboard -n mr-dashboard -- \
  wget -qO- http://localhost:8080/healthz
```

---

## 4. Updates de código

```bash
# 1. build e push
./build-and-push.sh

# 2. força rollout
kubectl rollout restart deployment/mr-dashboard -n mr-dashboard

# 3. acompanha
kubectl rollout status deployment/mr-dashboard -n mr-dashboard
```

---

## 5. Variáveis de ambiente (ConfigMap)

| Var | Default | Descrição |
|---|---|---|
| `API_GATEWAY_URL` | URL do API GW | URL regional interna do API Gateway |
| `PORT` | `8080` | Porta do gunicorn |
| `GUNICORN_WORKERS` | `2` | Workers gunicorn |
| `GUNICORN_THREADS` | `4` | Threads por worker |
| `PROXY_TIMEOUT` | `30` | Timeout em segundos pra chamar o API GW |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING |

Para alterar sem rebuild:
```bash
kubectl edit configmap mr-dashboard-config -n mr-dashboard
kubectl rollout restart deployment/mr-dashboard -n mr-dashboard
```

---

## 6. Troubleshooting

### Pod não sobe
```bash
kubectl describe pod -l app=mr-dashboard -n mr-dashboard
kubectl logs -l app=mr-dashboard -n mr-dashboard --previous
```

### Proxy retorna 502/504
```bash
# Testa resolução DNS de dentro do pod
kubectl exec -it deployment/mr-dashboard -n mr-dashboard -- \
  nslookup 5su5qmyoqc.execute-api.sa-east-1.amazonaws.com

# Deve retornar IP privado (10.x.x.x)
# Se retornar IP público ou falhar → NetworkPolicy bloqueando porta 53
#   ou Private DNS do VPCE não configurado
```

### ALB não cria
```bash
kubectl describe ingress mr-dashboard-ingress -n mr-dashboard
# Verifica logs do AWS Load Balancer Controller
kubectl logs -n kube-system deployment/aws-load-balancer-controller
```

### CORS ainda aparece no browser
```bash
# Confirma que o browser está batendo no Flask, não no API GW diretamente
# Network tab → Request URL deve ser o domínio do ALB, não vpce-... ou execute-api...
```

---

## Estrutura do projeto

```
mr-dashboard-eks/
├── Dockerfile              # multi-stage, non-root, produção
├── build-and-push.sh       # build ECR + push
├── app/
│   ├── app.py              # Flask BFF: serve HTML + proxy /api/dashboard
│   ├── requirements.txt    # flask, requests, gunicorn
│   └── static/
│       └── index.html      # dashboard (bate em /api/dashboard, não no API GW diretamente)
└── k8s/
    └── manifests.yaml      # Namespace, ConfigMap, Secret, Deployment,
                            # Service, HPA, Ingress (ALB), PDB, NetworkPolicy
```
