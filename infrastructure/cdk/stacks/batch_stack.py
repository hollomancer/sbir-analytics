"""AWS Batch stack for ML job execution."""

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_batch as batch,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class BatchStack(Stack):
    """AWS Batch infrastructure for running analysis jobs on-demand."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get or create ECR repository for analysis job images
        create_new = self.node.try_get_context("create_new_resources") == "true"

        if create_new:
            # Create new ECR repository
            self.ecr_repository = ecr.Repository(
                self,
                "AnalysisJobsRepository",
                repository_name="sbir-analytics-analysis-jobs",
                image_scan_on_push=True,
                lifecycle_rules=[
                    ecr.LifecycleRule(
                        description="Keep last 10 images",
                        max_image_count=10,
                        rule_priority=1,
                    )
                ],
            )
        else:
            # Import existing ECR repository
            repo_name = self.node.try_get_context("ecr_repository_name") or "sbir-analytics-analysis-jobs"
            self.ecr_repository = ecr.Repository.from_repository_name(
                self,
                "AnalysisJobsRepository",
                repository_name=repo_name,
            )

        # CloudWatch Log Group for Batch job logs
        log_group = logs.LogGroup(
            self,
            "BatchJobLogGroup",
            log_group_name="/aws/batch/sbir-analytics-analysis",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.RETAIN,  # Keep logs even if stack is deleted
        )

        # Use default VPC (simplest approach) or allow VPC ID to be specified
        vpc_id = self.node.try_get_context("vpc_id")
        if vpc_id:
            vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=vpc_id)
        else:
            # Use default VPC
            vpc = ec2.Vpc.from_lookup(self, "VPC", is_default=True)

        # Security group for Batch compute environment
        security_group = ec2.SecurityGroup(
            self,
            "BatchSecurityGroup",
            vpc=vpc,
            description="Security group for AWS Batch analysis job compute environment",
            allow_all_outbound=True,  # Need to pull Docker images from ECR and access S3
        )

        # IAM role for Batch service
        batch_service_role = iam.Role(
            self,
            "BatchServiceRole",
            assumed_by=iam.ServicePrincipal("batch.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSBatchServiceRole"
                )
            ],
        )

        # IAM role for EC2 instances in Batch compute environment
        instance_role = iam.Role(
            self,
            "BatchInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonEC2ContainerServiceforEC2Role"
                )
            ],
        )

        # Instance profile for EC2 instances
        instance_profile = iam.CfnInstanceProfile(
            self,
            "BatchInstanceProfile",
            roles=[instance_role.role_name],
            instance_profile_name="sbir-analytics-batch-instance-profile",
        )

        # IAM role for Batch jobs (execution role)
        job_execution_role = iam.Role(
            self,
            "BatchJobExecutionRole",
            role_name="sbir-analytics-batch-job-execution-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        # Add ECR pull permissions
        self.ecr_repository.grant_pull(job_execution_role)

        # IAM role for Batch job tasks (task role - what the job can do)
        job_task_role = iam.Role(
            self,
            "BatchJobTaskRole",
            role_name="sbir-analytics-batch-job-task-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        # Grant S3 access for reading input data and writing results
        job_task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:ListBucket",
                ],
                resources=[
                    "arn:aws:s3:::sbir-etl-production-data",
                    "arn:aws:s3:::sbir-etl-production-data/*",
                ],
            )
        )

        # Grant Secrets Manager access for Neo4j credentials
        job_task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:sbir-analytics/neo4j-aura*"
                ],
            )
        )

        # Compute environment using Spot instances (70% cost savings)
        compute_environment = batch.CfnComputeEnvironment(
            self,
            "AnalysisComputeEnvironment",
            type="MANAGED",
            service_role=batch_service_role.role_arn,
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                type="SPOT",
                allocation_strategy="SPOT_CAPACITY_OPTIMIZED",
                bid_percentage=100,  # Maximum spot price = on-demand price
                minv_cpus=0,  # Scale down to 0 when idle
                maxv_cpus=32,  # Maximum 32 vCPUs across all jobs
                desiredv_cpus=0,  # Start at 0
                instance_types=[
                    "c5.large",     # 2 vCPUs, 4 GB RAM - minimum viable
                    "c5.xlarge",    # 4 vCPUs, 8 GB RAM
                    "m5.large",     # 2 vCPUs, 8 GB RAM - more memory
                    "m5.xlarge",    # 4 vCPUs, 16 GB RAM
                ],
                subnets=[subnet.subnet_id for subnet in vpc.public_subnets],
                security_group_ids=[security_group.security_group_id],
                instance_role=instance_profile.attr_arn,
                tags={
                    "Name": "sbir-analytics-analysis-batch",
                    "ManagedBy": "CDK",
                },
            ),
            compute_environment_name="sbir-analytics-analysis-compute-env",
        )

        # Job queue
        job_queue = batch.CfnJobQueue(
            self,
            "AnalysisJobQueue",
            job_queue_name="sbir-analytics-analysis-job-queue",
            priority=1,
            compute_environment_order=[
                batch.CfnJobQueue.ComputeEnvironmentOrderProperty(
                    compute_environment=compute_environment.attr_compute_environment_arn,
                    order=1,
                )
            ],
        )

        # Job definition for CET pipeline
        cet_job_definition = batch.CfnJobDefinition(
            self,
            "CETJobDefinition",
            job_definition_name="sbir-analytics-analysis-cet-pipeline",
            type="container",
            platform_capabilities=["EC2"],
            container_properties=batch.CfnJobDefinition.ContainerPropertiesProperty(
                image=f"{self.ecr_repository.repository_uri}:latest",
                vcpus=2,
                memory=4096,  # 4 GB
                job_role_arn=job_task_role.role_arn,
                execution_role_arn=job_execution_role.role_arn,
                command=[
                    "dagster",
                    "job",
                    "execute",
                    "-m",
                    "src.definitions_ml",
                    "-j",
                    "cet_full_pipeline_job",
                ],
                environment=[
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="DAGSTER_LOAD_HEAVY_ASSETS",
                        value="true",
                    ),
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="DAGSTER_HOME",
                        value="/tmp/dagster_home",
                    ),
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="AWS_DEFAULT_REGION",
                        value=self.region,
                    ),
                ],
                log_configuration=batch.CfnJobDefinition.LogConfigurationProperty(
                    log_driver="awslogs",
                    options={
                        "awslogs-group": "/aws/batch/sbir-analytics-analysis",
                        "awslogs-stream-prefix": "cet",
                    },
                ),
            ),
            retry_strategy=batch.CfnJobDefinition.RetryStrategyProperty(
                attempts=2,  # Retry once on failure (Spot interruptions)
            ),
            timeout=batch.CfnJobDefinition.TimeoutProperty(
                attempt_duration_seconds=21600,  # 6 hours max
            ),
        )

        # Job definition for Fiscal Returns
        fiscal_job_definition = batch.CfnJobDefinition(
            self,
            "FiscalJobDefinition",
            job_definition_name="sbir-analytics-analysis-fiscal-returns",
            type="container",
            platform_capabilities=["EC2"],
            container_properties=batch.CfnJobDefinition.ContainerPropertiesProperty(
                image=f"{self.ecr_repository.repository_uri}:latest",
                vcpus=4,
                memory=8192,  # 8 GB
                job_role_arn=job_task_role.role_arn,
                execution_role_arn=job_execution_role.role_arn,
                command=[
                    "dagster",
                    "job",
                    "execute",
                    "-m",
                    "src.definitions_ml",
                    "-j",
                    "fiscal_returns_mvp_job",
                ],
                environment=[
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="DAGSTER_LOAD_HEAVY_ASSETS",
                        value="true",
                    ),
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="DAGSTER_HOME",
                        value="/tmp/dagster_home",
                    ),
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="AWS_DEFAULT_REGION",
                        value=self.region,
                    ),
                ],
                log_configuration=batch.CfnJobDefinition.LogConfigurationProperty(
                    log_driver="awslogs",
                    options={
                        "awslogs-group": "/aws/batch/sbir-analytics-analysis",
                        "awslogs-stream-prefix": "fiscal",
                    },
                ),
            ),
            retry_strategy=batch.CfnJobDefinition.RetryStrategyProperty(
                attempts=2,
            ),
            timeout=batch.CfnJobDefinition.TimeoutProperty(
                attempt_duration_seconds=14400,  # 4 hours max
            ),
        )

        # Job definition for PaECTER embeddings
        paecter_job_definition = batch.CfnJobDefinition(
            self,
            "PaecterJobDefinition",
            job_definition_name="sbir-analytics-analysis-paecter-embeddings",
            type="container",
            platform_capabilities=["EC2"],
            container_properties=batch.CfnJobDefinition.ContainerPropertiesProperty(
                image=f"{self.ecr_repository.repository_uri}:latest",
                vcpus=2,
                memory=4096,  # 4 GB for embeddings
                job_role_arn=job_task_role.role_arn,
                execution_role_arn=job_execution_role.role_arn,
                command=[
                    "dagster",
                    "job",
                    "execute",
                    "-m",
                    "src.definitions_ml",
                    "-j",
                    "paecter_job",
                ],
                environment=[
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="DAGSTER_LOAD_HEAVY_ASSETS",
                        value="true",
                    ),
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="DAGSTER_HOME",
                        value="/tmp/dagster_home",
                    ),
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="AWS_DEFAULT_REGION",
                        value=self.region,
                    ),
                ],
                log_configuration=batch.CfnJobDefinition.LogConfigurationProperty(
                    log_driver="awslogs",
                    options={
                        "awslogs-group": "/aws/batch/sbir-analytics-analysis",
                        "awslogs-stream-prefix": "paecter",
                    },
                ),
            ),
            retry_strategy=batch.CfnJobDefinition.RetryStrategyProperty(
                attempts=2,
            ),
            timeout=batch.CfnJobDefinition.TimeoutProperty(
                attempt_duration_seconds=21600,  # 6 hours max
            ),
        )

        # Outputs
        CfnOutput(self, "ECRRepositoryUri", value=self.ecr_repository.repository_uri)
        CfnOutput(self, "ECRRepositoryName", value=self.ecr_repository.repository_name)
        CfnOutput(self, "ComputeEnvironmentArn", value=compute_environment.attr_compute_environment_arn)
        CfnOutput(self, "JobQueueArn", value=job_queue.attr_job_queue_arn)
        CfnOutput(self, "JobQueueName", value=job_queue.job_queue_name)
        CfnOutput(self, "CETJobDefinitionArn", value=cet_job_definition.ref)
        CfnOutput(self, "FiscalJobDefinitionArn", value=fiscal_job_definition.ref)
        CfnOutput(self, "PaecterJobDefinitionArn", value=paecter_job_definition.ref)
        CfnOutput(self, "JobTaskRoleArn", value=job_task_role.role_arn)
        CfnOutput(self, "JobExecutionRoleArn", value=job_execution_role.role_arn)
