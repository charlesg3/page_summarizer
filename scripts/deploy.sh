#!/bin/bash

# Exit on any error
set -e

# Variables
SUFFIX="$(date +%Y%m%d%H%M%S)"
BUCKET_SUFFIX="20250330150643"
TEMPLATE_FILE="cloudformation/stack.yaml"
STACK_NAME="pagesum-${SUFFIX}"
S3_BUCKET="cloudytdl-${BUCKET_SUFFIX}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color


# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if template file exists
if [ ! -f "$TEMPLATE_FILE" ]; then
    echo "Error: Template file '$TEMPLATE_FILE' not found."
    exit 1
fi

echo -e "${YELLOW}Deploying CloudFormation stack '$STACK_NAME' using template '$TEMPLATE_FILE'...${NC}"

# Deploy the CloudFormation stack
aws cloudformation create-stack \
    --stack-name $STACK_NAME \
    --parameters \
    ParameterKey=S3BucketName,ParameterValue=$S3_BUCKET \
    --template-body file://$TEMPLATE_FILE \
    --capabilities CAPABILITY_IAM \

echo "Stack creation initiated. Waiting for stack to complete..."

# Function to check stack status
check_stack_status() {
    aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query 'Stacks[0].StackStatus' \
        --output text
}

# Poll until stack creation completes or fails
while true; do
    STATUS=$(check_stack_status)
    echo "Current status: $STATUS"
    
    # Check if the stack creation is complete
    if [[ "$STATUS" == "CREATE_COMPLETE" ]]; then
        echo "Stack creation completed successfully!"
        break
    # Check if the stack creation failed
    elif [[ "$STATUS" == "CREATE_FAILED" || "$STATUS" == "ROLLBACK_IN_PROGRESS" || "$STATUS" == "ROLLBACK_COMPLETE" ]]; then
        echo "Stack creation failed. Getting error details..."
        
        # Fetch and display stack events to identify the error
        aws cloudformation describe-stack-events \
            --stack-name $STACK_NAME \
            --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`].[LogicalResourceId,ResourceStatusReason]' \
            --output text

        echo "Stack deployment failed. See error details above."
        exit 1
    fi
    
    # Wait before checking again
    sleep 10
done

# Output stack outputs
echo "Stack outputs:"
aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs' \
    --output table

echo "Stack resources:"
aws cloudformation list-stack-resources \
    --stack-name $STACK_NAME \
    --query 'StackResourceSummaries[*].[LogicalResourceId,ResourceType,ResourceStatus]' \
    --output table

echo "Deployment completed successfully!"
