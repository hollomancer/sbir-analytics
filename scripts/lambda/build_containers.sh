#!/bin/bash
# Build and push Lambda container images to ECR

set -e

AWS_REGION="${AWS_REGION:-us-east-2}"
ECR_REPO="${ECR_REPO:-sbir-etl-lambda}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"

if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "Error: AWS_ACCOUNT_ID environment variable not set"
    exit 1
fi

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

echo "Building Lambda container images..."
echo "ECR Repository: ${ECR_URI}"

# Login to ECR
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_URI}"

# Build and push ingestion-checks
echo ""
echo "Building ingestion-checks container..."
cd lambda/containers/ingestion-checks
docker build -t "${ECR_URI}:ingestion-checks" .
docker tag "${ECR_URI}:ingestion-checks" "${ECR_URI}:ingestion-checks-latest"
docker push "${ECR_URI}:ingestion-checks"
docker push "${ECR_URI}:ingestion-checks-latest"
cd - > /dev/null

# Build and push load-neo4j
echo ""
echo "Building load-neo4j container..."
cd lambda/containers/load-neo4j
docker build -t "${ECR_URI}:load-neo4j" .
docker tag "${ECR_URI}:load-neo4j" "${ECR_URI}:load-neo4j-latest"
docker push "${ECR_URI}:load-neo4j"
docker push "${ECR_URI}:load-neo4j-latest"
cd - > /dev/null

echo ""
echo "Container images built and pushed successfully!"
echo "ECR URI: ${ECR_URI}"

