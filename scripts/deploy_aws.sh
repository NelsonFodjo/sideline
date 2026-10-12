#!/usr/bin/env bash
# Build the image, push it to ECR, deploy deploy/sideline.yaml.
#
#   scripts/deploy_aws.sh                       # defaults
#   STACK=sideline REGION=us-east-1 scripts/deploy_aws.sh
#   EXTRA="AuthMode=required AuthIssuer=... AuthAudience=... AuthJwksUrl=..." scripts/deploy_aws.sh
#
# Needs: docker running, `aws` configured (aws sts get-caller-identity works).
# Costs money: one App Runner instance (a few dollars a month idle).
# Tear down with:  aws cloudformation delete-stack --stack-name sideline
set -euo pipefail

STACK="${STACK:-sideline}"
REGION="${REGION:-${AWS_REGION:-us-east-1}}"
REPO="${REPO:-sideline}"
TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"
cd "$(dirname "$0")/.."

command -v docker >/dev/null || { echo "docker is not installed or not on PATH" >&2; exit 1; }
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
IMAGE="$REGISTRY/$REPO:$TAG"

echo "==> ECR repository $REPO"
aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null

echo "==> build and push $IMAGE"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"

echo "==> deploy stack $STACK"
# shellcheck disable=SC2086
aws cloudformation deploy \
  --region "$REGION" --stack-name "$STACK" \
  --template-file deploy/sideline.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides ImageUri="$IMAGE" ${EXTRA:-}

echo
aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
  --query "Stacks[0].Outputs" --output table
echo "Next: give <ServiceUrl>/mcp to the Alexa+ add-on (docs/ALEXA_SETUP.md)."
