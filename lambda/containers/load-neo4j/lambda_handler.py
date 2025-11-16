"""Lambda handler for load-neo4j container."""

# Copy the handler from scripts/lambda/load_neo4j/lambda_handler.py
# This file is included in the container image
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from load_neo4j.lambda_handler import lambda_handler

__all__ = ["lambda_handler"]

