#!/bin/bash
# Deploy Lambda function for weekly award data refresh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPO_NAME="sbir-etl/weekly-refresh"
LAMBDA_FUNCTION_NAME="sbir-weekly-refresh"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not found. Please install it first."
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker not found. Please install it first."
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Please run 'aws configure' first."
        exit 1
    fi
    
    log_info "Prerequisites check passed"
}

# Get AWS account ID
get_account_id() {
    aws sts get-caller-identity --query Account --output text
}

# Get ECR repository URL
get_ecr_url() {
    local account_id=$(get_account_id)
    echo "${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"
}

# Create ECR repository if it doesn't exist
ensure_ecr_repo() {
    log_info "Ensuring ECR repository exists..."
    
    if aws ecr describe-repositories --repository-names "${ECR_REPO_NAME}" --region "${AWS_REGION}" &> /dev/null; then
        log_info "ECR repository already exists"
    else
        log_info "Creating ECR repository..."
        aws ecr create-repository \
            --repository-name "${ECR_REPO_NAME}" \
            --region "${AWS_REGION}" \
            --image-scanning-configuration scanOnPush=true \
            --encryption-configuration encryptionType=AES256
        log_info "ECR repository created"
    fi
}

# Login to ECR
ecr_login() {
    log_info "Logging in to ECR..."
    aws ecr get-login-password --region "${AWS_REGION}" | \
        docker login --username AWS --password-stdin "$(get_ecr_url)"
    log_info "ECR login successful"
}

# Build Docker image
build_image() {
    log_info "Building Lambda container image..."
    
    local ecr_url=$(get_ecr_url)
    local image_uri="${ecr_url}:${IMAGE_TAG}"
    
    cd "${PROJECT_ROOT}"
    docker build \
        -f docker/lambda/Dockerfile \
        -t "${image_uri}" \
        .
    
    log_info "Image built: ${image_uri}"
    echo "${image_uri}"
}

# Push image to ECR
push_image() {
    local image_uri="$1"
    
    log_info "Pushing image to ECR..."
    docker push "${image_uri}"
    log_info "Image pushed successfully"
}

# Update Lambda function
update_lambda() {
    local image_uri="$1"
    
    log_info "Updating Lambda function..."
    
    aws lambda update-function-code \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --image-uri "${image_uri}" \
        --region "${AWS_REGION}" \
        --output json > /tmp/lambda-update.json
    
    log_info "Waiting for Lambda function update to complete..."
    aws lambda wait function-updated \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --region "${AWS_REGION}"
    
    log_info "Lambda function updated successfully"
    
    # Display function info
    local function_arn=$(jq -r '.FunctionArn' /tmp/lambda-update.json)
    log_info "Lambda function ARN: ${function_arn}"
}

# Main deployment flow
main() {
    log_info "Starting Lambda deployment..."
    
    check_prerequisites
    ensure_ecr_repo
    ecr_login
    
    local image_uri=$(build_image)
    push_image "${image_uri}"
    update_lambda "${image_uri}"
    
    log_info "Deployment completed successfully!"
    log_info "Lambda function: ${LAMBDA_FUNCTION_NAME}"
    log_info "Image URI: ${image_uri}"
}

# Run main function
main "$@"

