"""Step Functions state machine stack."""

import json
from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct


class StepFunctionsStack(Stack):
    """Step Functions state machine for SBIR ETL workflow."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        lambda_functions: dict,
        execution_role,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Load state machine definition from JSON file
        state_machine_path = Path(__file__).parent.parent.parent / "step-functions" / "weekly-refresh-state-machine.json"
        
        if state_machine_path.exists():
            with state_machine_path.open() as f:
                definition = json.load(f)
            # Replace Lambda ARN placeholders with actual function ARNs
            definition_str = json.dumps(definition)
            for func_name, func in lambda_functions.items():
                definition_str = definition_str.replace(
                    f"${{{{lambda.{func_name}.arn}}}}", func.function_arn
                )
            definition = json.loads(definition_str)
        else:
            # Fallback: Build state machine programmatically
            definition = self._build_state_machine_definition(lambda_functions)

        # Create Step Functions state machine
        self.state_machine = sfn.StateMachine(
            self,
            "WeeklyRefreshStateMachine",
            state_machine_name="sbir-etl-weekly-refresh",
            definition_body=sfn.DefinitionBody.from_string(json.dumps(definition)),
            role=execution_role,
            timeout=Duration.hours(2),
            tracing_enabled=True,
        )

        CfnOutput(self, "StateMachineArn", value=self.state_machine.state_machine_arn)

    def _build_state_machine_definition(self, lambda_functions: dict) -> dict:
        """Build state machine definition programmatically."""
        return {
            "Comment": "SBIR Weekly Awards Refresh Workflow",
            "StartAt": "DownloadCSV",
            "States": {
                "DownloadCSV": {
                    "Type": "Task",
                    "Resource": lambda_functions["download-csv"].function_arn,
                    "Next": "CheckChanges",
                    "Retry": [
                        {
                            "ErrorEquals": ["States.TaskFailed"],
                            "IntervalSeconds": 2,
                            "MaxAttempts": 3,
                            "BackoffRate": 2.0,
                        }
                    ],
                    "Catch": [
                        {
                            "ErrorEquals": ["States.ALL"],
                            "Next": "ErrorHandler",
                            "ResultPath": "$.error",
                        }
                    ],
                },
                "CheckChanges": {
                    "Type": "Choice",
                    "Choices": [
                        {
                            "Variable": "$.body.changed",
                            "BooleanEquals": True,
                            "Next": "ProcessPipeline",
                        },
                        {
                            "Variable": "$.force_refresh",
                            "BooleanEquals": True,
                            "Next": "ProcessPipeline",
                        },
                    ],
                    "Default": "EndNoChanges",
                },
                "ProcessPipeline": {
                    "Type": "Parallel",
                    "Branches": [
                        {
                            "StartAt": "ValidateDataset",
                            "States": {
                                "ValidateDataset": {
                                    "Type": "Task",
                                    "Resource": lambda_functions["validate-dataset"].function_arn,
                                    "End": True,
                                    "Retry": [
                                        {
                                            "ErrorEquals": ["States.TaskFailed"],
                                            "IntervalSeconds": 2,
                                            "MaxAttempts": 3,
                                        }
                                    ],
                                },
                            },
                        },
                        {
                            "StartAt": "ProfileInputs",
                            "States": {
                                "ProfileInputs": {
                                    "Type": "Task",
                                    "Resource": lambda_functions["profile-inputs"].function_arn,
                                    "End": True,
                                    "Retry": [
                                        {
                                            "ErrorEquals": ["States.TaskFailed"],
                                            "IntervalSeconds": 2,
                                            "MaxAttempts": 3,
                                        }
                                    ],
                                },
                            },
                        },
                    ],
                    "Next": "TriggerDagsterRefresh",
                },
                "TriggerDagsterRefresh": {
                    "Type": "Task",
                    "Resource": lambda_functions["trigger-dagster-refresh"].function_arn,
                    "Comment": "Triggers sbir_weekly_refresh_job in Dagster Cloud (replaces ingestion-checks and load-neo4j)",
                    "Next": "EnrichmentChecks",
                    "Retry": [
                        {
                            "ErrorEquals": ["States.TaskFailed"],
                            "IntervalSeconds": 5,
                            "MaxAttempts": 2,
                        }
                    ],
                },
                "EnrichmentChecks": {
                    "Type": "Task",
                    "Resource": lambda_functions["enrichment-checks"].function_arn,
                    "Next": "ResetNeo4j",
                    "Retry": [
                        {
                            "ErrorEquals": ["States.TaskFailed"],
                            "IntervalSeconds": 2,
                            "MaxAttempts": 3,
                        }
                    ],
                },
                "ResetNeo4j": {
                    "Type": "Task",
                    "Resource": lambda_functions["reset-neo4j"].function_arn,
                    "Next": "SmokeChecks",
                    "Retry": [
                        {
                            "ErrorEquals": ["States.TaskFailed"],
                            "IntervalSeconds": 2,
                            "MaxAttempts": 2,
                        }
                    ],
                },
                "SmokeChecks": {
                    "Type": "Task",
                    "Resource": lambda_functions["smoke-checks"].function_arn,
                    "End": True,
                    "Retry": [
                        {
                            "ErrorEquals": ["States.TaskFailed"],
                            "IntervalSeconds": 2,
                            "MaxAttempts": 3,
                        }
                    ],
                },
                "EndNoChanges": {
                    "Type": "Succeed",
                    "Comment": "No changes detected, skipping processing",
                },
                "ErrorHandler": {
                    "Type": "Fail",
                    "Error": "WorkflowError",
                    "Cause": "An error occurred in the workflow",
                },
            },
        }

