#!/bin/bash
# Add Lambda layer permissions to GitHub Actions role

set -e

ROLE_NAME="sbir-etl-github-actions-role"
REGION="us-east-2"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "Adding Lambda layer permissions to role: $ROLE_NAME"

# Create inline policy for Lambda layer operations
aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "LambdaLayerManagement" \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "lambda:PublishLayerVersion",
          "lambda:GetLayerVersion",
          "lambda:DeleteLayerVersion"
        ],
        "Resource": "arn:aws:lambda:'"$REGION"':'"$ACCOUNT_ID"':layer:sbir-analytics-*"
      }
    ]
  }'

echo "✅ Lambda layer permissions added successfully"
