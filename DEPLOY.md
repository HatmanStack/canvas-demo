# Deploying Canvas Demo to AWS Lambda

This guide covers deploying the application as a containerized Lambda function using CodeBuild and ECR.

## Architecture Overview

```text
S3 (source zip) --> CodeBuild --> ECR (Docker image) --> Lambda (container)
```

- **CodeBuild** builds the Docker image from source and pushes it to ECR
- **Lambda** pulls the container image from ECR and runs it via the Lambda Web Adapter
- There is no IaC (CloudFormation, SAM, Terraform) — resources are created manually

## Prerequisites

- AWS CLI configured with appropriate permissions
- An ECR repository (e.g., `production/canvas-demo`)
- An S3 bucket for CodeBuild source and app data (e.g., `nova-image-data`)

## 1. IAM Role Setup

### Lambda Execution Role

Create a Lambda execution role with the following policies:

**Trust policy:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

**Attached policies:**

- `AmazonBedrockFullAccess` (AWS managed) — for Nova Canvas and Nova Lite model access
- `AWSLambdaBasicExecutionRole` (AWS managed) — for CloudWatch Logs
- Inline S3 policy for your image bucket:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::YOUR-BUCKET-NAME",
        "arn:aws:s3:::YOUR-BUCKET-NAME/*"
      ]
    }
  ]
}
```

### Credentials

The Lambda uses its execution role for all AWS access — **do not set `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` as environment variables**. Lambda auto-injects these as STS temporary credentials that require a session token; passing them explicitly without the token causes auth failures.

For local development, set `AMP_AWS_ID` and `AMP_AWS_SECRET` in your `.env` file. These are the only credential env vars the app reads explicitly.

## 2. Lambda Configuration

### Create the Lambda function

Create a container-image Lambda function pointing to your ECR image:

```bash
aws lambda create-function \
  --function-name canvas-demo \
  --package-type Image \
  --code ImageUri=<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/production/canvas-demo:latest \
  --role arn:aws:iam::<ACCOUNT_ID>:role/service-role/<YOUR-ROLE-NAME> \
  --timeout 300 \
  --memory-size 1024 \
  --region <REGION>
```

### Environment variables

Set the following environment variables on the Lambda (do not include AWS credentials):

| Variable | Description | Example |
|---|---|---|
| `NOVA_IMAGE_BUCKET` | S3 bucket for image storage and rate limiting | `nova-image-data` |
| `BUCKET_REGION` | Region of the S3 bucket | `us-west-2` |
| `RATE_LIMIT` | Max requests per 20-minute sliding window | `20` |
| `HF_TOKEN` | HuggingFace token for NSFW detection (optional) | `hf_...` |
| `AWS_LWA_READINESS_CHECK_PATH` | Lambda Web Adapter health check path | `/healthz` |

```bash
aws lambda update-function-configuration \
  --function-name canvas-demo \
  --region <REGION> \
  --environment "Variables={NOVA_IMAGE_BUCKET=nova-image-data,BUCKET_REGION=us-west-2,RATE_LIMIT=20,HF_TOKEN=your-token,AWS_LWA_READINESS_CHECK_PATH=/healthz}"
```

### Function URL

Enable a function URL for public HTTP access:

```bash
aws lambda create-function-url-config \
  --function-name canvas-demo \
  --auth-type NONE \
  --region <REGION>
```

## 3. CodeBuild Setup

### Create the CodeBuild project

- **Source**: S3 (not GitHub webhook — builds are manual)
- **Environment**: Linux container, `aws/codebuild/amazonlinux-x86_64-standard:5.0`
- **Compute**: `BUILD_GENERAL1_SMALL` (sufficient for Docker builds)
- **Privileged mode**: May be required for Docker-in-Docker builds
- **Environment variable**: Set `AWS_ACCOUNT_ID` to your account ID

The CodeBuild service role needs permissions to:

- Pull from the S3 source bucket
- Push to the ECR repository
- Write CloudWatch Logs

### buildspec.yaml

The `buildspec.yaml` in the repo handles the build pipeline:

1. Logs into ECR
2. Builds the Docker image
3. Pushes to `production/canvas-demo:latest`

The `AWS_ACCOUNT_ID` environment variable must be set on the CodeBuild project (it is not hardcoded in the buildspec).

## 4. Build and Deploy

### Zip the source

```bash
zip -r canvas-demo-build.zip \
  app.py buildspec.yaml Dockerfile requirements.txt seeds.json \
  src/ static/ uv.lock pyproject.toml \
  -x "*/__pycache__/*" "*.pyc" "src/canvas_demo.egg-info/*"
```

### Upload and build

```bash
# Upload source to S3
aws s3 cp canvas-demo-build.zip s3://nova-image-data/codebuild/canvas-demo-build.zip

# Start the CodeBuild build
aws codebuild start-build \
  --project-name canvas-demo \
  --region <REGION> \
  --source-type-override S3 \
  --source-location-override nova-image-data/codebuild/canvas-demo-build.zip
```

### Update the Lambda

CodeBuild pushes the image to ECR but does **not** automatically update the Lambda. After the build completes:

```bash
aws lambda update-function-code \
  --function-name canvas-demo \
  --region <REGION> \
  --image-uri <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/production/canvas-demo:latest
```

## Troubleshooting

### "The security token included in the request is invalid"

This usually means explicit AWS credentials are being passed without the STS session token. Ensure `AMP_AWS_ID`, `AMP_AWS_SECRET`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` are **not** set as Lambda environment variables. The execution role provides credentials automatically.

### Lambda Web Adapter readiness warnings

The logs may show `app is not ready after Xms` during cold starts. This is normal — the adapter polls `/healthz` while Gradio initializes. The adapter will begin routing traffic after the app starts or after its timeout.

### CodeBuild Docker failures

If the build fails on `docker build`, ensure privileged mode is enabled on the CodeBuild project:

```bash
aws codebuild update-project --name canvas-demo --region <REGION> \
  --environment "type=LINUX_CONTAINER,image=aws/codebuild/amazonlinux-x86_64-standard:5.0,computeType=BUILD_GENERAL1_SMALL,privilegedMode=true"
```
