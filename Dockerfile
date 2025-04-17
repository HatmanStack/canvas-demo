# Dockerfile

# Use an official Python runtime as a parent image (choose version matching your needs)
FROM public.ecr.aws/docker/library/python:3.12-slim


ENV RATE_LIMIT=20
ENV NOVA_IMAGE_BUCKET=nova-image-data
ENV BUCKET_REGION=us-west-2
WORKDIR /app
RUN --mount=type=secret,id=amp_aws_id \
    --mount=type=secret,id=amp_aws_secret \
    --mount=type=secret,id=hf_token \
    AMP_AWS_ID=$(cat /run/secrets/amp_aws_id) && \
    AMP_AWS_SECRET=$(cat /run/secrets/amp_aws_secret) && \
    HF_TOKEN=$(cat /run/secrets/hf_token)

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ARG TARGETARCH=amd64

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.0 /lambda-adapter /opt/extensions/lambda-adapter

CMD ["python3", "app.py"]

