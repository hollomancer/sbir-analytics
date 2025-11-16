# Lambda function for weekly SBIR award data refresh

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ECR repository for Lambda container image
resource "aws_ecr_repository" "lambda_weekly_refresh" {
  name                 = "sbir-etl/weekly-refresh"
  image_tag_mutability = "MUTABLE"
  
  image_scanning_configuration {
    scan_on_push = true
  }
  
  encryption_configuration {
    encryption_type = "AES256"
  }
}

# IAM role for Lambda function
resource "aws_iam_role" "lambda_weekly_refresh" {
  name = "sbir-weekly-refresh-lambda-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# IAM policy for Lambda function
resource "aws_iam_role_policy" "lambda_weekly_refresh" {
  name = "sbir-weekly-refresh-lambda-policy"
  role = aws_iam_role.lambda_weekly_refresh.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:HeadObject"
        ]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket}",
          "arn:aws:s3:::${var.s3_bucket}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = var.neo4j_secret_arn != null ? [var.neo4j_secret_arn] : []
      }
    ]
  })
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda_weekly_refresh" {
  name              = "/aws/lambda/sbir-weekly-refresh"
  retention_in_days = 30
}

# Lambda function
resource "aws_lambda_function" "weekly_refresh" {
  function_name = "sbir-weekly-refresh"
  role          = aws_iam_role.lambda_weekly_refresh.arn
  timeout       = 900  # 15 minutes max
  memory_size   = 3008  # Max memory for container image
  
  package_type = "Image"
  image_uri     = "${aws_ecr_repository.lambda_weekly_refresh.repository_url}:latest"
  
  environment {
    variables = {
      S3_BUCKET         = var.s3_bucket
      NEO4J_SECRET_NAME = var.neo4j_secret_name
      DEFAULT_SOURCE_URL = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"
    }
  }
  
  depends_on = [
    aws_cloudwatch_log_group.lambda_weekly_refresh,
    aws_iam_role_policy.lambda_weekly_refresh
  ]
}

# Variables
variable "s3_bucket" {
  description = "S3 bucket name for storing CSV files and metadata"
  type        = string
}

variable "neo4j_secret_name" {
  description = "Secrets Manager secret name for Neo4j credentials (optional)"
  type        = string
  default     = null
}

variable "neo4j_secret_arn" {
  description = "Secrets Manager secret ARN for Neo4j credentials (optional)"
  type        = string
  default     = null
}

# Outputs
output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.weekly_refresh.function_name
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.weekly_refresh.arn
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.lambda_weekly_refresh.repository_url
}

output "lambda_role_arn" {
  description = "IAM role ARN for Lambda function"
  value       = aws_iam_role.lambda_weekly_refresh.arn
}

