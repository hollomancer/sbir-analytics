"""EC2 development environment stack.

Provisions a single EC2 instance for containerized development,
replacing local Docker Compose as the primary dev target.
The instance runs the full docker-compose stack (Dagster + DuckDB)
without Neo4j as a hard dependency.
"""

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class Ec2DevStack(Stack):
    """EC2 instance for containerized SBIR Analytics development."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        s3_bucket=None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Configuration from context ---
        instance_type_str = self.node.try_get_context("instance_type") or "t3.medium"
        key_pair_name = self.node.try_get_context("key_pair_name")
        allowed_ssh_cidr = self.node.try_get_context("allowed_ssh_cidr") or "0.0.0.0/0"
        volume_size_gb = int(self.node.try_get_context("volume_size_gb") or "50")

        # --- VPC ---
        vpc_id = self.node.try_get_context("vpc_id")
        if vpc_id:
            vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=vpc_id)
        else:
            vpc = ec2.Vpc.from_lookup(self, "VPC", is_default=True)

        # --- Security Group ---
        sg = ec2.SecurityGroup(
            self,
            "DevInstanceSG",
            vpc=vpc,
            description="SBIR Analytics EC2 dev instance",
            allow_all_outbound=True,
        )
        # SSH
        sg.add_ingress_rule(
            ec2.Peer.ipv4(allowed_ssh_cidr),
            ec2.Port.tcp(22),
            "SSH access",
        )
        # Dagster UI
        sg.add_ingress_rule(
            ec2.Peer.ipv4(allowed_ssh_cidr),
            ec2.Port.tcp(3000),
            "Dagster webserver",
        )
        # NeoDash (optional visualization)
        sg.add_ingress_rule(
            ec2.Peer.ipv4(allowed_ssh_cidr),
            ec2.Port.tcp(5005),
            "NeoDash dashboard",
        )

        # --- IAM Role ---
        role = iam.Role(
            self,
            "DevInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                # SSM for Session Manager access (no SSH key needed)
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
        )

        # S3 access for data
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                resources=[
                    "arn:aws:s3:::sbir-etl-production-data",
                    "arn:aws:s3:::sbir-etl-production-data/*",
                ],
            )
        )

        # Secrets Manager for any credentials
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:sbir-analytics/*"
                ],
            )
        )

        # ECR / GHCR pull (for pre-built images)
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],
            )
        )

        # CloudWatch Logs for instance logs
        log_group = logs.LogGroup(
            self,
            "DevInstanceLogGroup",
            log_group_name="/sbir-analytics/ec2-dev",
            removal_policy=RemovalPolicy.DESTROY,
        )

        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                ],
                resources=[log_group.log_group_arn + ":*"],
            )
        )

        # --- User Data (bootstrap script) ---
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "#!/bin/bash",
            "set -euo pipefail",
            "",
            "# System updates",
            "yum update -y",
            "",
            "# Install Docker",
            "yum install -y docker git",
            "systemctl enable docker",
            "systemctl start docker",
            "usermod -aG docker ec2-user",
            "",
            "# Install Docker Compose V2",
            'COMPOSE_VERSION="v2.29.1"',
            "mkdir -p /usr/local/lib/docker/cli-plugins",
            'curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" '
            '-o /usr/local/lib/docker/cli-plugins/docker-compose',
            "chmod +x /usr/local/lib/docker/cli-plugins/docker-compose",
            "",
            "# Install AWS CLI v2 (if not present)",
            "if ! command -v aws &> /dev/null; then",
            '  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip',
            "  unzip -q /tmp/awscliv2.zip -d /tmp",
            "  /tmp/aws/install",
            "  rm -rf /tmp/aws /tmp/awscliv2.zip",
            "fi",
            "",
            "# Clone repository",
            "sudo -u ec2-user bash -c '",
            "  cd /home/ec2-user",
            "  if [ ! -d sbir-analytics ]; then",
            "    git clone https://github.com/hollomancer/sbir-analytics.git",
            "  fi",
            "  cd sbir-analytics",
            "",
            "  # Create .env with defaults",
            '  cat > .env << \'ENVEOF\'',
            "ENVIRONMENT=dev",
            "COMPOSE_PROFILES=ec2-dev",
            "NEO4J_USER=neo4j",
            "NEO4J_PASSWORD=dev-password",
            "DAGSTER_PORT=3000",
            "ENVEOF",
            "'",
            "",
            "echo 'EC2 dev environment bootstrap complete'",
            "echo 'Run: cd /home/ec2-user/sbir-analytics && docker compose --profile ec2-dev up -d'",
        )

        # --- EC2 Instance ---
        instance = ec2.Instance(
            self,
            "DevInstance",
            instance_type=ec2.InstanceType(instance_type_str),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=sg,
            role=role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size_gb,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                    ),
                )
            ],
            key_pair=ec2.KeyPair.from_key_pair_name(
                self, "KeyPair", key_pair_name
            ) if key_pair_name else None,
        )

        # --- Outputs ---
        CfnOutput(self, "InstanceId", value=instance.instance_id)
        CfnOutput(
            self,
            "PublicIp",
            value=instance.instance_public_ip or "N/A (no public IP)",
        )
        CfnOutput(
            self,
            "SSMConnect",
            value=f"aws ssm start-session --target {instance.instance_id} --region {self.region}",
            description="Connect via SSM Session Manager (no SSH key needed)",
        )
        CfnOutput(
            self,
            "DagsterUI",
            value=f"http://<instance-ip>:3000",
            description="Dagster webserver URL (replace <instance-ip> with PublicIp)",
        )
