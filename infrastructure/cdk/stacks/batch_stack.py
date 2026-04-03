"""AWS Batch stack for ML job execution."""

from dataclasses import dataclass

from aws_cdk import (
    CfnOutput,
    Stack,
    aws_batch as batch,
    aws_ec2 as ec2,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
)
from constructs import Construct

from stacks.config import (
    ANALYSIS_IMAGE,
    BATCH_COMPUTE_ENV_NAME,
    BATCH_JOB_EXECUTION_ROLE_NAME,
    BATCH_JOB_QUEUE_NAME,
    BATCH_JOB_TASK_ROLE_NAME,
    BATCH_LOG_GROUP,
    NEO4J_SECRET_NAME,
    S3_BUCKET_NAME,
)


@dataclass
class JobConfig:
    """Configuration for a Batch job definition."""

    id: str
    name: str
    command: list[str]
    vcpus: str = "2"
    memory_mb: str = "4096"
    timeout_seconds: int = 21600  # 6 hours
    log_prefix: str = ""
    ephemeral_storage_gib: int | None = None
    extra_env: list[dict] | None = None

    @property
    def log_stream_prefix(self) -> str:
        return self.log_prefix or self.name.split("-")[-1]


class BatchStack(Stack):
    """AWS Batch infrastructure for running analysis jobs on-demand."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # CloudWatch Log Group for Batch job logs (import existing)
        logs.LogGroup.from_log_group_name(
            self, "BatchJobLogGroup", log_group_name=BATCH_LOG_GROUP,
        )

        # VPC setup
        vpc_id = self.node.try_get_context("vpc_id")
        vpc = (
            ec2.Vpc.from_lookup(self, "VPC", vpc_id=vpc_id)
            if vpc_id
            else ec2.Vpc.from_lookup(self, "VPC", is_default=True)
        )

        security_group = ec2.SecurityGroup(
            self, "BatchSecurityGroup", vpc=vpc,
            description="Security group for AWS Batch analysis job compute environment",
            allow_all_outbound=True,
        )

        # IAM roles
        batch_service_role = iam.Role(
            self, "BatchServiceRole",
            assumed_by=iam.ServicePrincipal("batch.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSBatchServiceRole"
                )
            ],
        )

        instance_role = iam.Role(
            self, "BatchInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonEC2ContainerServiceforEC2Role"
                )
            ],
        )

        iam.CfnInstanceProfile(
            self, "BatchInstanceProfile",
            roles=[instance_role.role_name],
            instance_profile_name="sbir-analytics-batch-instance-profile",
        )

        job_execution_role = iam.Role(
            self, "BatchJobExecutionRole",
            role_name=BATCH_JOB_EXECUTION_ROLE_NAME,
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        job_task_role = iam.Role(
            self, "BatchJobTaskRole",
            role_name=BATCH_JOB_TASK_ROLE_NAME,
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        job_task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                resources=[
                    f"arn:aws:s3:::{S3_BUCKET_NAME}",
                    f"arn:aws:s3:::{S3_BUCKET_NAME}/*",
                ],
            )
        )

        neo4j_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "Neo4jSecretRef", secret_name=NEO4J_SECRET_NAME,
        )
        neo4j_secret.grant_read(job_task_role)

        # Compute environment (Fargate)
        compute_environment = batch.CfnComputeEnvironment(
            self, "AnalysisComputeEnvironment",
            type="MANAGED",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                type="FARGATE",
                maxv_cpus=8,
                subnets=[subnet.subnet_id for subnet in vpc.public_subnets],
                security_group_ids=[security_group.security_group_id],
            ),
            compute_environment_name=BATCH_COMPUTE_ENV_NAME,
        )

        job_queue = batch.CfnJobQueue(
            self, "AnalysisJobQueue",
            job_queue_name=BATCH_JOB_QUEUE_NAME,
            priority=1,
            compute_environment_order=[
                batch.CfnJobQueue.ComputeEnvironmentOrderProperty(
                    compute_environment=compute_environment.attr_compute_environment_arn,
                    order=1,
                )
            ],
        )

        # --- Job definitions ---
        common_dagster_env = [
            {"name": "DAGSTER_LOAD_HEAVY_ASSETS", "value": "true"},
            {"name": "DAGSTER_HOME", "value": "/tmp/dagster_home"},
        ]

        jobs = [
            JobConfig(
                id="CETJobDefinition",
                name="sbir-analytics-analysis-cet-pipeline",
                command=["dagster", "job", "execute", "-m", "sbir_etl.definitions_ml", "-j", "cet_full_pipeline_job"],
                vcpus="2", memory_mb="4096",
                timeout_seconds=21600,  # 6 hours
                log_prefix="cet",
                extra_env=common_dagster_env,
            ),
            JobConfig(
                id="FiscalJobDefinition",
                name="sbir-analytics-analysis-fiscal-returns",
                command=["dagster", "job", "execute", "-m", "sbir_etl.definitions_ml", "-j", "fiscal_returns_mvp_job"],
                vcpus="4", memory_mb="8192",
                timeout_seconds=14400,  # 4 hours
                log_prefix="fiscal",
                extra_env=common_dagster_env,
            ),
            JobConfig(
                id="PaecterJobDefinition",
                name="sbir-analytics-analysis-paecter-embeddings",
                command=["dagster", "job", "execute", "-m", "sbir_etl.definitions_ml", "-j", "paecter_job"],
                vcpus="2", memory_mb="4096",
                timeout_seconds=21600,  # 6 hours
                log_prefix="paecter",
                extra_env=common_dagster_env,
            ),
            JobConfig(
                id="UsaspendingExtractJobDefinition",
                name="sbir-analytics-usaspending-extract",
                command=[
                    "bash", "-c",
                    f'cd /app && python scripts/usaspending/download_database.py --source-url "${{USASPENDING_URL}}" --s3-bucket {S3_BUCKET_NAME}',
                ],
                vcpus="4", memory_mb="30720",
                timeout_seconds=28800,  # 8 hours
                log_prefix="usaspending-extract",
                ephemeral_storage_gib=200,
            ),
        ]

        job_definitions = {}
        for job in jobs:
            job_definitions[job.id] = self._create_job_definition(
                job, job_task_role, job_execution_role,
            )

        # Outputs
        CfnOutput(self, "AnalysisImage", value=ANALYSIS_IMAGE)
        CfnOutput(self, "ComputeEnvironmentArn", value=compute_environment.attr_compute_environment_arn)
        CfnOutput(self, "JobQueueArn", value=job_queue.attr_job_queue_arn)
        CfnOutput(self, "JobQueueName", value=job_queue.job_queue_name)
        CfnOutput(self, "CETJobDefinitionArn", value=job_definitions["CETJobDefinition"].ref)
        CfnOutput(self, "FiscalJobDefinitionArn", value=job_definitions["FiscalJobDefinition"].ref)
        CfnOutput(self, "PaecterJobDefinitionArn", value=job_definitions["PaecterJobDefinition"].ref)
        CfnOutput(self, "UsaspendingExtractJobDefinitionArn", value=job_definitions["UsaspendingExtractJobDefinition"].ref)
        CfnOutput(self, "JobTaskRoleArn", value=job_task_role.role_arn)
        CfnOutput(self, "JobExecutionRoleArn", value=job_execution_role.role_arn)

        # SNS notifications for job state changes
        notification_topic = sns.Topic(
            self, "BatchJobNotifications",
            display_name="SBIR Analytics Batch Job Notifications",
        )

        notification_email = self.node.try_get_context("notification_email")
        if notification_email:
            notification_topic.add_subscription(
                subscriptions.EmailSubscription(notification_email)
            )

        events.Rule(
            self, "BatchJobStateChangeRule",
            event_pattern=events.EventPattern(
                source=["aws.batch"],
                detail_type=["Batch Job State Change"],
                detail={
                    "status": ["SUCCEEDED", "FAILED"],
                    "jobQueue": [job_queue.attr_job_queue_arn],
                },
            ),
            targets=[targets.SnsTopic(notification_topic)],
        )

        CfnOutput(self, "NotificationTopicArn", value=notification_topic.topic_arn)

    def _create_job_definition(
        self,
        config: JobConfig,
        job_task_role: iam.Role,
        job_execution_role: iam.Role,
    ) -> batch.CfnJobDefinition:
        """Create a Fargate Batch job definition from a JobConfig."""
        env_vars = [
            batch.CfnJobDefinition.EnvironmentProperty(
                name="AWS_DEFAULT_REGION", value=self.region,
            ),
        ]
        for entry in config.extra_env or []:
            env_vars.append(
                batch.CfnJobDefinition.EnvironmentProperty(
                    name=entry["name"], value=entry["value"],
                )
            )

        container_props = batch.CfnJobDefinition.ContainerPropertiesProperty(
            image=ANALYSIS_IMAGE,
            resource_requirements=[
                batch.CfnJobDefinition.ResourceRequirementProperty(type="VCPU", value=config.vcpus),
                batch.CfnJobDefinition.ResourceRequirementProperty(type="MEMORY", value=config.memory_mb),
            ],
            job_role_arn=job_task_role.role_arn,
            execution_role_arn=job_execution_role.role_arn,
            network_configuration=batch.CfnJobDefinition.NetworkConfigurationProperty(
                assign_public_ip="ENABLED",
            ),
            command=config.command,
            environment=env_vars,
            log_configuration=batch.CfnJobDefinition.LogConfigurationProperty(
                log_driver="awslogs",
                options={
                    "awslogs-group": BATCH_LOG_GROUP,
                    "awslogs-stream-prefix": config.log_stream_prefix,
                },
            ),
            **(
                {"ephemeral_storage": batch.CfnJobDefinition.EphemeralStorageProperty(
                    size_in_gib=config.ephemeral_storage_gib,
                )}
                if config.ephemeral_storage_gib
                else {}
            ),
        )

        return batch.CfnJobDefinition(
            self,
            config.id,
            job_definition_name=config.name,
            type="container",
            platform_capabilities=["FARGATE"],
            container_properties=container_props,
            retry_strategy=batch.CfnJobDefinition.RetryStrategyProperty(attempts=2),
            timeout=batch.CfnJobDefinition.TimeoutProperty(
                attempt_duration_seconds=config.timeout_seconds,
            ),
        )
