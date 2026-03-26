FROM public.ecr.aws/docker/library/python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies using lock file for reproducibility
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-dev --no-editable

COPY src/ src/
COPY app.py seeds.json ./
COPY static/ static/

ARG TARGETARCH=amd64

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.0 /lambda-adapter /opt/extensions/lambda-adapter

CMD ["python3", "app.py"]
