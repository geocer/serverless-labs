#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# build-and-push.sh — build da imagem Docker e push pro ECR
# Uso: ./build-and-push.sh [TAG]
#   TAG: opcional, default = git short hash ou 'latest'
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

# ── CONFIGURAÇÃO ────────────────────────────────────────────────────────────
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-262041882421}"    # sua conta
AWS_REGION="${AWS_REGION:-sa-east-1}"
ECR_REPO="mr-dashboard"
IMAGE_NAME="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
TAG="${1:-$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')}"

echo "╔══════════════════════════════════════════════╗"
echo "║  MR Dashboard — Build & Push                ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Account : ${AWS_ACCOUNT_ID}"
echo "║  Region  : ${AWS_REGION}"
echo "║  Image   : ${IMAGE_NAME}:${TAG}"
echo "╚══════════════════════════════════════════════╝"

# ── 1. Login no ECR ─────────────────────────────────────────────────────────
echo ""
echo "▶ [1/4] Login no ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# ── 2. Criar repositório ECR se não existir ─────────────────────────────────
echo ""
echo "▶ [2/4] Verificando repositório ECR..."
aws ecr describe-repositories \
  --repository-names "${ECR_REPO}" \
  --region "${AWS_REGION}" \
  --query 'repositories[0].repositoryUri' \
  --output text 2>/dev/null || \
aws ecr create-repository \
  --repository-name "${ECR_REPO}" \
  --region "${AWS_REGION}" \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256 \
  --query 'repository.repositoryUri' \
  --output text

echo "  ✓ Repositório: ${IMAGE_NAME}"

# ── 3. Build da imagem ──────────────────────────────────────────────────────
echo ""
echo "▶ [3/4] Build da imagem Docker..."
docker build \
  --platform linux/amd64 \
  --tag "${IMAGE_NAME}:${TAG}" \
  --tag "${IMAGE_NAME}:latest" \
  --cache-from "${IMAGE_NAME}:latest" \
  --build-arg BUILDKIT_INLINE_CACHE=1 \
  .

echo "  ✓ Build concluído: ${IMAGE_NAME}:${TAG}"

# ── 4. Push pro ECR ─────────────────────────────────────────────────────────
echo ""
echo "▶ [4/4] Push pro ECR..."
docker push "${IMAGE_NAME}:${TAG}"
docker push "${IMAGE_NAME}:latest"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  ✅  Push concluído!                        ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  ${IMAGE_NAME}:${TAG}"
echo "║  ${IMAGE_NAME}:latest"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Próximo passo — atualiza o Deployment no EKS:"
echo ""
echo "  # Opção A — aplica os manifests (primeira vez)"
echo "  kubectl apply -f k8s/manifests.yaml"
echo ""
echo "  # Opção B — força rollout sem alterar manifests (updates)"
echo "  kubectl set image deployment/mr-dashboard \\"
echo "    mr-dashboard=${IMAGE_NAME}:${TAG} \\"
echo "    -n mr-dashboard"
echo ""
echo "  # Acompanha o rollout"
echo "  kubectl rollout status deployment/mr-dashboard -n mr-dashboard"
