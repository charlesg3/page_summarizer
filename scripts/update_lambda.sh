#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Print colored status messages
function log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

function log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

function log_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

function log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

function log_step() {
  echo -e "\n${CYAN}${BOLD}=== $1 ===${NC}\n"
}

# Configuration
AWS_REGION=$(aws configure get region)


ECR_REPOSITORY_NAME="webpage-summarize"
LAMBDA_FUNCTION_NAME="webpage-summarizer"
DOCKERFILE_PATH="docker/Dockerfile"
DOCKER_CONTEXT_PATH="."  # Context path for docker build

# Get AWS account ID
log_step "Getting AWS Account ID"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log_info "AWS Account ID: ${BOLD}$AWS_ACCOUNT_ID${NC}"

# Build the Docker image
log_step "Building Docker Image"
log_info "Building Docker image from $DOCKERFILE_PATH..."
docker build -t $ECR_REPOSITORY_NAME -f $DOCKERFILE_PATH $DOCKER_CONTEXT_PATH
log_success "Docker image built successfully."

# Check if ECR repository exists, create if it doesn't
log_step "Preparing ECR Repository"
if ! aws ecr describe-repositories --repository-names $ECR_REPOSITORY_NAME --region $AWS_REGION >/dev/null 2>&1; then
  log_info "Creating ECR repository: $ECR_REPOSITORY_NAME..."
  aws ecr create-repository --repository-name $ECR_REPOSITORY_NAME --region $AWS_REGION
  log_success "ECR repository created successfully."
else
  log_info "ECR repository ${BOLD}$ECR_REPOSITORY_NAME${NC} already exists."
fi

# Get ECR login token and authenticate Docker client
log_step "Authenticating Docker with ECR"
log_info "Authenticating Docker with ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
log_success "Authentication successful."

# Tag the image for ECR
log_step "Tagging and Pushing Image to ECR"
ECR_IMAGE_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY_NAME:latest"
log_info "Tagging Docker image as ${BOLD}$ECR_IMAGE_URI${NC}..."
docker tag $ECR_REPOSITORY_NAME:latest $ECR_IMAGE_URI
log_success "Image tagged successfully."

# Push the image to ECR
log_info "Pushing Docker image to ECR..."
docker push $ECR_IMAGE_URI
log_success "Image pushed successfully to ECR."

# Update Lambda function to use the new container image
log_step "Updating Lambda Function"
log_info "Updating Lambda function ${BOLD}$LAMBDA_FUNCTION_NAME${NC} with the new image..."
UPDATE_OUTPUT=$(aws lambda update-function-code \
  --function-name $LAMBDA_FUNCTION_NAME \
  --image-uri $ECR_IMAGE_URI \
  --region $AWS_REGION \
  --output json)

# Extract the Last Update Status
UPDATE_STATUS=$(echo $UPDATE_OUTPUT | grep -o '"LastUpdateStatus": "[^"]*"' | cut -d '"' -f 4)
log_info "Lambda update initiated. Current status: ${BOLD}$UPDATE_STATUS${NC}"

# Wait for the function to finish updating
log_step "Waiting for Lambda Update to Complete"
log_info "Waiting for Lambda function update to complete..."

WAIT_TIME=0
MAX_WAIT_TIME=300  # Maximum wait time in seconds (5 minutes)
INTERVAL=5         # Check status every 5 seconds

while [ "$UPDATE_STATUS" = "InProgress" ] && [ $WAIT_TIME -lt $MAX_WAIT_TIME ]; do
  sleep $INTERVAL
  WAIT_TIME=$((WAIT_TIME + INTERVAL))
  
  # Get the current status
  UPDATE_STATUS=$(aws lambda get-function \
    --function-name $LAMBDA_FUNCTION_NAME \
    --region $AWS_REGION \
    --query 'Configuration.LastUpdateStatus' \
    --output text)
  
  log_info "Lambda update status: ${BOLD}$UPDATE_STATUS${NC} (waited ${WAIT_TIME}s)"
done

# Check final status
if [ "$UPDATE_STATUS" = "Successful" ]; then
  log_success "Lambda function updated successfully!"
elif [ "$UPDATE_STATUS" = "InProgress" ] && [ $WAIT_TIME -ge $MAX_WAIT_TIME ]; then
  log_warning "Lambda update is still in progress after ${MAX_WAIT_TIME}s. Please check the AWS Console for final status."
else
  log_error "Lambda update failed with status: ${UPDATE_STATUS}"
  # Get the failure reason if available
  FAILURE_REASON=$(aws lambda get-function \
    --function-name $LAMBDA_FUNCTION_NAME \
    --region $AWS_REGION \
    --query 'Configuration.LastUpdateStatusReasonCode' \
    --output text)
  
  if [ "$FAILURE_REASON" != "None" ] && [ "$FAILURE_REASON" != "null" ]; then
    log_error "Failure reason: ${BOLD}$FAILURE_REASON${NC}"
  fi
  exit 1
fi

# Get the current function version
FUNCTION_VERSION=$(aws lambda get-function \
  --function-name $LAMBDA_FUNCTION_NAME \
  --region $AWS_REGION \
  --query 'Configuration.Version' \
  --output text)


log_step "Deployment Summary"
echo -e "${GREEN}${BOLD}✓ Deployment completed successfully!${NC}"
echo -e "${MAGENTA}• Image:${NC} $ECR_IMAGE_URI"
echo -e "${MAGENTA}• Lambda:${NC} $LAMBDA_FUNCTION_NAME"
echo -e "${MAGENTA}• Region:${NC} $AWS_REGION"
