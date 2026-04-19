"""Batch stack: Fargate compute environments, job queue, job definitions, SNS notifications."""

from dataclasses import dataclass

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_batch as batch,
    aws_ec2 as ec2,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
)
from constructs import Construct

from stacks.config import (
    ANALYSIS_IMAGE,
    BATCH_COMPUTE_ENV_ON_DEMAND,
    BATCH_COMPUTE_ENV_SPOT,
    BATCH_JOB_EXECUTION_ROLE_NAME,
    BATCH_JOB_QUEUE_NAME,
    BATCH_JOB_TASK_ROLE_NAME,
    BATCH_LOG_GROUP,
    S3_BUCKET_NAME,
)


@dataclass
class JobConfig:
    """Configuration for a single Batch job definition."""

    id: str
    name: str
    command: list[str]
    vcpus: str = "2"
    memory_mb: str = "4096"
    timeout_seconds: int = 21600
    log_prefix: str = ""
    ephemeral_storage_gib: int | None = None
    extra_env: list[dict] | None = None

    @property
    def log_stream_prefix(self) -> str:
        return self.log_prefix or self.name.split("-")[-1]


_DAGSTER_ENV = [
    {"name": "DAGSTER_LOAD_HEAVY_ASSETS", "value": "true"},
    {"name": "DAGSTER_HOME", "value": "/tmp/dagster_home"},
]

_JOB_CONFIGS = [
    JobConfig(
        id="CETJob",
        name="sbir-analytics-cet-pipeline",
        command=[
            "dagster", "job", "execute",
            "-m", "sbir_analytics.definitions_ml",
            "-j", "cet_full_pipeline_job",
        ],
        vcpus="2",
        memory_mb="4096",
        timeout_seconds=21600,
        log_prefix="cet",
        extra_env=_DAGSTER_ENV,
    ),
    JobConfig(
        id="FiscalJob",
        name="sbir-analytics-fiscal-returns",
        command=[
            "dagster", "job", "execute",
            "-m", "sbir_analytics.definitions_ml",
            "-j", "fiscal_returns_mvp_job",
        ],
        vcpus="4",
        memory_mb="8192",
        timeout_seconds=14400,
        log_prefix="fiscal",
        extra_env=_DAGSTER_ENV,
    ),
    JobConfig(
        id="PaecterJob",
        name="sbir-analytics-paecter-embeddings",
        command=[
            "dagster", "job", "execute",
            "-m", "sbir_analytics.definitions_ml",
            "-j", "paecter_job",
        ],
        vcpus="2",
        memory_mb="4096",
        timeout_seconds=21600,
        log_prefix="paecter",
        extra_env=_DAGSTER_ENV,
    ),
    JobConfig(
        id="UsaspendingExtractJob",
        name="sbir-analytics-usaspending-extract",
        command=[
            "bash", "-c",
            f'cd /app && python scripts/usaspending/download_database.py'
            f' --source-url "${{USASPENDING_URL}}"'
            f" --s3-bucket {S3_BUCKET_NAME}",
        ],
        vcpus="4",
        memory_mb="30720",
        timeout_seconds=28800,
        log_prefix="usaspending-extract",
        ephemeral_storage_gib=200,
    ),
]


class BatchStack(Stack):
    """AWS Batch infrastructure for running analysis jobs on-demand."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        bucket: s3.IBucket,
        neo4j_secret: secretsmanager.ISecret,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        log_group = logs.LogGroup(
            self,
            "BatchLogGroup",
            log_group_name=BATCH_LOG_GROUP,
            retention=logs.RetentionDays.THREE_MONTHS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        vpc = ec2.Vpc.from_lookup(self, "VPC", is_default=True)

        security_group = ec2.SecurityGroup(
            self,
            "BatchSG",
            vpc=vpc,
            description="SBIR Analytics Batch job security group",
            allow_all_outbound=True,
        )

        execution_role = iam.Role(
            self,
            "BatchExecutionRole",
            role_name=BATCH_JOB_EXECUTION_ROLE_NAME,
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        task_role = iam.Role(
            self,
            "BatchTaskRole",
            role_name=BATCH_JOB_TASK_ROLE_NAME,
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                resources=[bucket.bucket_arn, bucket.bucket_arn + "/*"],
            )
        )
        neo4j_secret.grant_read(task_role)

        compute_spot = batch.CfnComputeEnvironment(
            self,
            "ComputeSpot",
            type="MANAGED",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                type="FARGATE_SPOT",
                maxv_cpus=8,
                subnets=[s.subnet_id for s in vpc.public_subnets],
                security_group_ids=[security_group.security_group_id],
            ),
            compute_environment_name=BATCH_COMPUTE_ENV_SPOT,
        )

        compute_on_demand = batch.CfnComputeEnvironment(
            self,
            "ComputeOnDemand",
            type="MANAGED",
            compute_resources=batch.CfnComputeEnvironment.ComputeResourcesProperty(
                type="FARGATE",
                maxv_cpus=8,
                subnets=[s.subnet_id for s in vpc.public_subnets],
                security_group_ids=[security_group.security_group_id],
            ),
            compute_environment_name=BATCH_COMPUTE_ENV_ON_DEMAND,
        )

        job_queue = batch.CfnJobQueue(
            self,
            "JobQueue",
            job_queue_name=BATCH_JOB_QUEUE_NAME,
            priority=1,
            compute_environment_order=[
                batch.CfnJobQueue.ComputeEnvironmentOrderProperty(
                    compute_environment=compute_spot.attr_compute_environment_arn,
                    order=1,
                ),
                batch.CfnJobQueue.ComputeEnvironmentOrderProperty(
                    compute_environment=compute_on_demand.attr_compute_environment_arn,
                    order=2,
                ),
            ],
        )

        for job in _JOB_CONFIGS:
            self._define_job(job, task_role, execution_role, log_group)

        notification_topic = sns.Topic(
            self,
            "BatchNotifications",
            display_name="SBIR Analytics Batch Notifications",
        )

        notification_email = self.node.try_get_context("notification_email")
        if notification_email:
            notification_topic.add_subscription(
                subscriptions.EmailSubscription(notification_email)
            )

        events.Rule(
            self,
            "BatchStateChangeRule",
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

        CfnOutput(self, "JobQueueName", value=job_queue.job_queue_name)
        CfnOutput(self, "NotificationTopicArn", value=notification_topic.topic_arn)

    def _define_job(
        self,
        config: JobConfig,
        task_role: iam.Role,
        execution_role: iam.Role,
        log_group: logs.LogGroup,
    ) -> batch.CfnJobDefinition:
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
                batch.CfnJobDefinition.ResourceRequirementProperty(
                    type="VCPU", value=config.vcpus,
                ),
                batch.CfnJobDefinition.ResourceRequirementProperty(
                    type="MEMORY", value=config.memory_mb,
                ),
            ],
            job_role_arn=task_role.role_arn,
            execution_role_arn=execution_role.role_arn,
            network_configuration=batch.CfnJobDefinition.NetworkConfigurationProperty(
                assign_public_ip="ENABLED",
            ),
            command=config.command,
            environment=env_vars,
            log_configuration=batch.CfnJobDefinition.LogConfigurationProperty(
                log_driver="awslogs",
                options={
                    "awslogs-group": log_group.log_group_name,
                    "awslogs-stream-prefix": config.log_stream_prefix,
                },
            ),
            **(
                {
                    "ephemeral_storage": batch.CfnJobDefinition.EphemeralStorageProperty(
                        size_in_gib=config.ephemeral_storage_gib,
                    )
                }
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
