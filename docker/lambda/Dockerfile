# Lambda container image for weekly award data refresh
# Based on AWS Lambda Python 3.11 runtime
FROM public.ecr.aws/lambda/python:3.11

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Install system dependencies
RUN yum install -y curl && \
    yum clean all && \
    rm -rf /var/cache/yum

# Install UV
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    cp $HOME/.cargo/bin/uv /usr/local/bin/uv && \
    chmod +x /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install project dependencies using UV
# Export to requirements.txt and install with pip (Lambda-compatible)
RUN uv pip compile pyproject.toml --no-dev -o /tmp/requirements.txt && \
    pip install --no-cache-dir -r /tmp/requirements.txt || \
    uv sync --frozen --no-dev && \
    uv pip install --system -e . --no-deps

# Copy application code
COPY src/ ${LAMBDA_TASK_ROOT}/src/
COPY config/ ${LAMBDA_TASK_ROOT}/config/
COPY scripts/ ${LAMBDA_TASK_ROOT}/scripts/
COPY docs/ ${LAMBDA_TASK_ROOT}/docs/

# Set Python path
ENV PYTHONPATH=${LAMBDA_TASK_ROOT}

# Set Lambda handler
CMD ["src.lambda.weekly_refresh_handler.lambda_handler"]

