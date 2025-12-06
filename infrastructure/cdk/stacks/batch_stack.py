"""AWS Batch stack for ML job execution."""

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_batch as batch,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class BatchStack(Stack):
    """AWS Batch infrastructure for running analysis jobs on-demand."""

    # GHCR image for analysis jobs
    ANALYSIS_IMAGE = "ghcr.io/hollomancer/sbir-analytics-full:latest"

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # CloudWatch Log Group for Batch job logs (import existing or create)
        log_group = logs.LogGroup.from_log_group_name(
            self,
            "BatchJobLogGroup",
            log_group_name="/aws/batch/sbir-analytics-analysis",
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
            allow_all_outbound=True,  # Need to pull Docker images and access S3
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

        # Compute environment using Fargate (serverless)
        # Avoids EC2 instance type restrictions and quota issues
        compute_environment = batch.CfnComputeEnvironment(
            self,
            "AnalysisComputeEnvironment",
            type="MANAGED",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                type="FARGATE",
                maxv_cpus=8,  # Limit to 8 vCPUs to control costs
                subnets=[subnet.subnet_id for subnet in vpc.public_subnets],
                security_group_ids=[security_group.security_group_id],
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

        # Job definition for CET pipeline (Fargate)
        cet_job_definition = batch.CfnJobDefinition(
            self,
            "CETJobDefinition",
            job_definition_name="sbir-analytics-analysis-cet-pipeline",
            type="container",
            platform_capabilities=["FARGATE"],
            container_properties=batch.CfnJobDefinition.ContainerPropertiesProperty(
                image=self.ANALYSIS_IMAGE,
                resource_requirements=[
                    batch.CfnJobDefinition.ResourceRequirementProperty(type="VCPU", value="2"),
                    batch.CfnJobDefinition.ResourceRequirementProperty(type="MEMORY", value="4096"),
                ],
                job_role_arn=job_task_role.role_arn,
                execution_role_arn=job_execution_role.role_arn,
                network_configuration=batch.CfnJobDefinition.NetworkConfigurationProperty(
                    assign_public_ip="ENABLED",
                ),
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
                attempts=2,  # Retry once on failure
            ),
            timeout=batch.CfnJobDefinition.TimeoutProperty(
                attempt_duration_seconds=21600,  # 6 hours max
            ),
        )

        # Job definition for Fiscal Returns (Fargate)
        fiscal_job_definition = batch.CfnJobDefinition(
            self,
            "FiscalJobDefinition",
            job_definition_name="sbir-analytics-analysis-fiscal-returns",
            type="container",
            platform_capabilities=["FARGATE"],
            container_properties=batch.CfnJobDefinition.ContainerPropertiesProperty(
                image=self.ANALYSIS_IMAGE,
                resource_requirements=[
                    batch.CfnJobDefinition.ResourceRequirementProperty(type="VCPU", value="4"),
                    batch.CfnJobDefinition.ResourceRequirementProperty(type="MEMORY", value="8192"),
                ],
                job_role_arn=job_task_role.role_arn,
                execution_role_arn=job_execution_role.role_arn,
                network_configuration=batch.CfnJobDefinition.NetworkConfigurationProperty(
                    assign_public_ip="ENABLED",
                ),
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

        # Job definition for PaECTER embeddings (Fargate)
        paecter_job_definition = batch.CfnJobDefinition(
            self,
            "PaecterJobDefinition",
            job_definition_name="sbir-analytics-analysis-paecter-embeddings",
            type="container",
            platform_capabilities=["FARGATE"],
            container_properties=batch.CfnJobDefinition.ContainerPropertiesProperty(
                image=self.ANALYSIS_IMAGE,
                resource_requirements=[
                    batch.CfnJobDefinition.ResourceRequirementProperty(type="VCPU", value="2"),
                    batch.CfnJobDefinition.ResourceRequirementProperty(type="MEMORY", value="4096"),
                ],
                job_role_arn=job_task_role.role_arn,
                execution_role_arn=job_execution_role.role_arn,
                network_configuration=batch.CfnJobDefinition.NetworkConfigurationProperty(
                    assign_public_ip="ENABLED",
                ),
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

        # Job definition for USAspending recipient extraction (Fargate)
        # Extracts recipient_lookup table from 217GB dump → small parquet
        usaspending_extract_job_definition = batch.CfnJobDefinition(
            self,
            "UsaspendingExtractJobDefinition",
            job_definition_name="sbir-analytics-usaspending-extract",
            type="container",
            platform_capabilities=["FARGATE"],
            container_properties=batch.CfnJobDefinition.ContainerPropertiesProperty(
                image=self.ANALYSIS_IMAGE,
                resource_requirements=[
                    # Needs enough memory for 217GB ZIP download + processing
                    batch.CfnJobDefinition.ResourceRequirementProperty(type="VCPU", value="4"),
                    batch.CfnJobDefinition.ResourceRequirementProperty(type="MEMORY", value="30720"),  # 30GB
                ],
                job_role_arn=job_task_role.role_arn,
                execution_role_arn=job_execution_role.role_arn,
                network_configuration=batch.CfnJobDefinition.NetworkConfigurationProperty(
                    assign_public_ip="ENABLED",
                ),
                command=[
                    "bash",
                    "-c",
                    "cd /app && set -x && df -h && python scripts/data/extract_usaspending_batch.py --url \"${USASPENDING_URL}\" --s3-bucket sbir-etl-production-data",
                ],
                environment=[
                    batch.CfnJobDefinition.EnvironmentProperty(
                        name="AWS_DEFAULT_REGION",
                        value=self.region,
                    ),
                ],
                log_configuration=batch.CfnJobDefinition.LogConfigurationProperty(
                    log_driver="awslogs",
                    options={
                        "awslogs-group": "/aws/batch/sbir-analytics-analysis",
                        "awslogs-stream-prefix": "usaspending-extract",
                    },
                ),
                # Fargate ephemeral storage max is 200GB
                ephemeral_storage=batch.CfnJobDefinition.EphemeralStorageProperty(
                    size_in_gib=200,  # Max Fargate ephemeral storage
                ),
            ),
            retry_strategy=batch.CfnJobDefinition.RetryStrategyProperty(
                attempts=2,
            ),
            timeout=batch.CfnJobDefinition.TimeoutProperty(
                attempt_duration_seconds=7200,  # 2 hours max
            ),
        )

        # Outputs
        CfnOutput(self, "AnalysisImage", value=self.ANALYSIS_IMAGE)
        CfnOutput(self, "ComputeEnvironmentArn", value=compute_environment.attr_compute_environment_arn)
        CfnOutput(self, "JobQueueArn", value=job_queue.attr_job_queue_arn)
        CfnOutput(self, "JobQueueName", value=job_queue.job_queue_name)
        CfnOutput(self, "CETJobDefinitionArn", value=cet_job_definition.ref)
        CfnOutput(self, "FiscalJobDefinitionArn", value=fiscal_job_definition.ref)
        CfnOutput(self, "PaecterJobDefinitionArn", value=paecter_job_definition.ref)
        CfnOutput(self, "UsaspendingExtractJobDefinitionArn", value=usaspending_extract_job_definition.ref)
        CfnOutput(self, "JobTaskRoleArn", value=job_task_role.role_arn)
        CfnOutput(self, "JobExecutionRoleArn", value=job_execution_role.role_arn)
