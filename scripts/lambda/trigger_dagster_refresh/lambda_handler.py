"""Lambda function to trigger Dagster Cloud job execution via API."""

import json
import os
from typing import Any, Dict

import boto3
import requests

secrets_client = boto3.client("secretsmanager")


def get_dagster_cloud_token(secret_name: str) -> str:
    """Get Dagster Cloud API token from Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response["SecretString"])
    return secret["dagster_cloud_api_token"]


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Trigger sbir_weekly_refresh_job in Dagster Cloud.
    
    Event structure:
    {
        "dagster_cloud_org": "your-org",
        "dagster_cloud_deployment": "prod",
        "job_name": "sbir_weekly_refresh_job",
        "dagster_cloud_secret_name": "sbir-etl/dagster-cloud-api-token"  # Optional
    }
    """
    try:
        # Get configuration from event or environment
        org = event.get("dagster_cloud_org") or os.environ.get("DAGSTER_CLOUD_ORG")
        deployment = event.get("dagster_cloud_deployment") or os.environ.get("DAGSTER_CLOUD_DEPLOYMENT", "prod")
        job_name = event.get("job_name", "sbir_weekly_refresh_job")
        secret_name = event.get("dagster_cloud_secret_name") or os.environ.get("DAGSTER_CLOUD_SECRET_NAME", "sbir-etl/dagster-cloud-api-token")
        
        if not org:
            raise ValueError("dagster_cloud_org required in event or DAGSTER_CLOUD_ORG environment variable")
        
        # Get API token from Secrets Manager
        api_token = get_dagster_cloud_token(secret_name)
        
        # Construct Dagster Cloud API URL
        # Format: https://api.dagster.cloud/organizations/{org}/deployments/{deployment}/runs
        api_url = f"https://api.dagster.cloud/organizations/{org}/deployments/{deployment}/runs"
        
        # Prepare request
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        
        # Get run config from event if provided
        run_config = event.get("run_config", {})
        
        payload = {
            "job_name": job_name,
            "run_config": run_config,
        }
        
        # Add tags if provided
        if "tags" in event:
            payload["tags"] = event["tags"]
        
        print(f"Triggering Dagster Cloud job: {job_name} in {org}/{deployment}")
        print(f"API URL: {api_url}")
        
        # Make API request
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        run_data = response.json()
        run_id = run_data.get("runId") or run_data.get("id")
        
        print(f"Successfully triggered run: {run_id}")
        
        return {
            "statusCode": 200,
            "body": {
                "status": "success",
                "run_id": run_id,
                "job_name": job_name,
                "org": org,
                "deployment": deployment,
                "dagster_cloud_url": f"https://dagster.cloud/{org}/{deployment}/runs/{run_id}",
            },
        }
    
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to trigger Dagster Cloud job: {e}"
        if hasattr(e, "response") and e.response is not None:
            error_msg += f" (Status: {e.response.status_code}, Response: {e.response.text})"
        print(error_msg)
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": error_msg,
            },
        }
    
    except Exception as e:
        print(f"Error triggering Dagster Cloud job: {e}")
        import traceback
        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e),
            },
        }

