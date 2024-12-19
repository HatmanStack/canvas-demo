import os
import base64
import boto3
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from functools import wraps
from botocore.config import Config
from botocore.exceptions import ClientError

load_dotenv()
# Move custom exceptions to the top
class ImageError(Exception):
    def __init__(self, message):
        self.message = message

def handle_bedrock_errors(func):
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ClientError as err:
            logger.error(f"Bedrock client error: {err.response['Error']['Message']}")
            raise ImageError(f"Client error: {err.response['Error']['Message']}")
        except Exception as err:
            logger.error(f"Unexpected error: {str(err)}")
            raise ImageError(f"Unexpected error: {str(err)}")
    return wrapper

aws_id = os.getenv('AWS_ID')
aws_secret = os.getenv('AWS_SECRET')
rate_limit = int(os.getenv('RATE_LIMIT'))
nova_image_bucket='nova-image-data'
bucket_region='us-west-2'
rate_limit_message = """<div style='text-align: center;'>Rate limit exceeded. Check back later, use the 
            <a href='https://docs.aws.amazon.com/bedrock/latest/userguide/playgrounds.html'>Bedrock Playground</a> or
            try it out without an AWS account on <a href='https://partyrock.aws/'>PartyRock</a>.</div>"""

# Function to generate an image using Amazon Nova Canvas model
class BedrockClient:

    def __init__(self, aws_id, aws_secret, model_id, timeout=300):
        self.model_id = model_id
        self.bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            aws_access_key_id=aws_id,
            aws_secret_access_key=aws_secret,
            region_name='us-east-1',
            config=Config(read_timeout=timeout)
        )
        self.s3_client = boto3.client(
            service_name='s3',
            aws_access_key_id=aws_id,
            aws_secret_access_key=aws_secret,
            region_name=bucket_region
        )

    def _store_response(self, response_body, image_data=None):
        """Store response and image in S3."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Store response body
        response_key = f'responses/{timestamp}_response.json'
        self.s3_client.put_object(
            Bucket=nova_image_bucket,
            Key=response_key,
            Body=json.dumps(response_body),
            ContentType='application/json'
        )
        
        # Store image if present
        if image_data:
            image_key = f'images/{timestamp}_image.png'
            self.s3_client.put_object(
                Bucket=nova_image_bucket,
                Key=image_key,
                Body=image_data,
                ContentType='image/png'
            )
    
    
    def _handle_error(self, err):
        """Handle client errors"""
        raise ImageError(f"Client error: {err.response['Error']['Message']}")
    
    def generate_image(self, body):
        """Generate image using Bedrock service."""
        try:
            response = self.bedrock_client.invoke_model(
                body=body,
                modelId=self.model_id,
                accept="application/json",
                contentType="application/json"
            )
            image_data =  self._process_response(response)

            self._store_response(
                body,
                image_data
            )

            return image_data
        except ClientError as err:
            self._handle_error(err)
    
    @handle_bedrock_errors
    def generate_prompt(self, body):
        try:
            response = self.bedrock_client.converse(
                modelId=self.model_id, 
                messages=body
            )
            return self._process_response(response)
        except ClientError as err:
            self._handle_error(err)

    @handle_bedrock_errors
    def _process_response(self, response):
        """Process successful response for both image and text."""
        if "error" in response:
            raise ImageError(f"Generation error: {response['error']}")
        
        if "output" in response and "message" in response["output"]:
            message_content = response["output"]["message"]["content"]
            if message_content and "text" in message_content[0]:
                return message_content[0]["text"]

        response_body = json.loads(response.get("body").read())    
        if "images" in response_body:
            return base64.b64decode(response_body.get("images")[0].encode('ascii'))
        
        raise ImageError("Unexpected response format.")

def check_rate_limit(body):
    body = json.loads(body)
    quality = body.get('imageGenerationConfig', {}).get('quality', 'standard')
    
    s3_client = boto3.client(
        service_name='s3',
        aws_access_key_id=os.getenv('AWS_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET'),
        region_name=bucket_region
    )
    
    try:
        # Get current rate limit data
        response = s3_client.get_object(
            Bucket=nova_image_bucket,
            Key='rate-limit/jsonData.json'
        )
        rate_data = json.loads(response['Body'].read().decode('utf-8'))
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            # Initialize if file doesn't exist
            rate_data = {'premium': [], 'standard': []}
        else:
            raise ImageError(f"Failed to check rate limit: {str(e)}")

    # Get current timestamp
    current_time = datetime.now().timestamp()
    # Keep only requests from last minute
    twenty_minutes_ago = current_time - 1200
    
    # Clean up old entries
    rate_data['premium'] = [t for t in rate_data['premium'] if t > twenty_minutes_ago]
    rate_data['standard'] = [t for t in rate_data['standard'] if t > twenty_minutes_ago]

    # Calculate the total count of requests in the last 20 minutes
    total_count = len(rate_data['premium']) * 2 + len(rate_data['standard'])

    # Check limits based on quality
    if quality == 'premium':
        if total_count + 2 > rate_limit:  # Check if adding 2 would exceed the threshold
            raise ImageError(rate_limit_message)
        rate_data['premium'].append(current_time)
    else:  # standard
        if total_count + 1 > rate_limit:  # Check if adding 1 would exceed the threshold
            raise ImageError(rate_limit_message)
        rate_data['standard'].append(current_time)
    
    # Update rate limit file
    s3_client.put_object(
        Bucket=nova_image_bucket,
        Key='rate-limit/jsonData.json',
        Body=json.dumps(rate_data),
        ContentType='application/json'
    )
    

def generate_image(body):
    """Generate image using Bedrock service."""
    try:
        check_rate_limit(body)
        client = BedrockClient(
            aws_id=os.getenv('AWS_ID'),
            aws_secret=os.getenv('AWS_SECRET'),
            model_id='amazon.nova-canvas-v1:0'
        )
        return client.generate_image(body)
    except ImageError as e:
        return str(e)
        

def generate_prompt(body):
    client = BedrockClient(
        aws_id=os.getenv('AWS_ID'),
        aws_secret=os.getenv('AWS_SECRET'),
        model_id='us.amazon.nova-lite-v1:0'
    )
    return client.generate_prompt(body)
    