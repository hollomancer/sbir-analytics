#!/bin/bash
# Recover CloudFormation stack from UPDATE_ROLLBACK_FAILED state

set -e

STACK_NAME="${1:-sbir-analytics-lambda}"
REGION="${2:-us-east-2}"

echo "Checking stack status for: $STACK_NAME"

# Get current stack status
STATUS=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query 'Stacks[0].StackStatus' \
  --output text 2>/dev/null || echo "DOES_NOT_EXIST")

echo "Current status: $STATUS"

if [ "$STATUS" = "UPDATE_ROLLBACK_FAILED" ]; then
  echo "Stack is in UPDATE_ROLLBACK_FAILED state. Attempting to continue rollback..."

  aws cloudformation continue-update-rollback \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

  echo "Rollback continuation initiated. Waiting for completion..."

  aws cloudformation wait stack-rollback-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION" || true

  echo "Rollback complete. Stack should now be in ROLLBACK_COMPLETE state."
  echo "You can now delete and recreate the stack, or update it."

elif [ "$STATUS" = "ROLLBACK_COMPLETE" ]; then
  echo "Stack is in ROLLBACK_COMPLETE state. Deleting stack..."

  aws cloudformation delete-stack \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

  echo "Waiting for stack deletion..."
  aws cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

  echo "Stack deleted successfully. You can now redeploy."

else
  echo "Stack is in $STATUS state. No recovery needed."
fi
