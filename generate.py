import os
import base64
import boto3
import json
import logging
from datetime import datetime # Ensure datetime is imported
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
            logger.error(f"Bedrock client error in {func.__name__}: {err.response['Error']['Message']}")
            raise ImageError(f"Client error: {err.response['Error']['Message']}")
        except Exception as err:
            logger.error(f"Unexpected error in {func.__name__}: {str(err)}")
            raise ImageError(f"Unexpected error: {str(err)}")
    return wrapper

amp_aws_id = os.getenv('AMP_AWS_ID')
aws_secret = os.getenv('AMP_AWS_SECRET')
# Add default for rate_limit if env var is missing
rate_limit = int(os.getenv('RATE_LIMIT', 20))
nova_image_bucket=os.getenv('NOVA_IMAGE_BUCKET')
bucket_region=os.getenv('BUCKET_REGION')
rate_limit_message = """<div style='text-align: center;'>Rate limit exceeded. Check back later, use the
            <a href='https://docs.aws.amazon.com/bedrock/latest/userguide/playgrounds.html'>Bedrock Playground</a> or
            try it out without an AWS account on <a href='https://partyrock.aws/'>PartyRock</a>.</div>"""

# Function to generate an image using Amazon Nova Canvas model
class BedrockClient:

    def __init__(self, aws_id, aws_secret, model_id, timeout=300):
        print(f"[{datetime.now()}] Initializing BedrockClient...")
        self.model_id = model_id
        self.bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            aws_access_key_id=aws_id,
            aws_secret_access_key=aws_secret,
            region_name='us-east-1', # Assuming Bedrock is us-east-1
            config=Config(read_timeout=timeout)
        )
        self.s3_client = boto3.client(
            service_name='s3',
            aws_access_key_id=aws_id,
            aws_secret_access_key=aws_secret,
            region_name=bucket_region
        )
        print(f"[{datetime.now()}] BedrockClient initialized.")

    def _store_response(self, response_body, image_data=None):
        """Store response and image in S3."""
        print(f"[{datetime.now()}] Storing response/image to S3...")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f') # Added microseconds for uniqueness

        # Store response body
        response_key = f'responses/{timestamp}_response.json'
        self.s3_client.put_object(
            Bucket=nova_image_bucket,
            Key=response_key,
            Body=json.dumps(response_body), # Ensure body is JSON string
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
        print(f"[{datetime.now()}] Stored response/image to S3.")


    def _handle_error(self, err):
        """Handle client errors"""
        print(f"[{datetime.now()}] Handling ClientError: {err.response['Error']['Message']}")
        raise ImageError(f"Client error: {err.response['Error']['Message']}")

    @handle_bedrock_errors
    def generate_image(self, body):
        """Generate image using Bedrock service."""
        print(f"[{datetime.now()}] Calling Bedrock invoke_model ({self.model_id})...")
        # Ensure body is bytes if invoke_model expects it, or string if it expects JSON string
        body_bytes = body.encode('utf-8') if isinstance(body, str) else body
        response = self.bedrock_client.invoke_model(
            body=body_bytes,
            modelId=self.model_id,
            accept="application/json",
            contentType="application/json"
        )
        print(f"[{datetime.now()}] Bedrock invoke_model finished.")

        print(f"[{datetime.now()}] Processing Bedrock response...")
        image_data = self._process_response(response)
        print(f"[{datetime.now()}] Finished processing response.")

        # Parse the original body string back to dict for storage if needed
        body_dict_for_storage = json.loads(body) if isinstance(body, str) else body # Adjust if body isn't always JSON string
        self._store_response(
            body_dict_for_storage,
            image_data
        )
        return image_data
        # Error handling is now done by the decorator

    @handle_bedrock_errors
    def generate_prompt(self, body):
        print(f"[{datetime.now()}] Calling Bedrock converse ({self.model_id})...")
        response = self.bedrock_client.converse(
            modelId=self.model_id,
            messages=body # Assuming body is already the correct format for converse
        )
        print(f"[{datetime.now()}] Bedrock converse finished.")

        print(f"[{datetime.now()}] Processing Bedrock response...")
        result = self._process_response(response)
        print(f"[{datetime.now()}] Finished processing response.")
        return result
        # Error handling is now done by the decorator

    # Removed @handle_bedrock_errors here as it's called internally by decorated methods
    def _process_response(self, response):
        """Process successful response for both image and text."""
        # Handle converse response structure
        if "output" in response and "message" in response["output"]:
            message_content = response["output"]["message"]["content"]
            if message_content and isinstance(message_content, list) and len(message_content) > 0 and "text" in message_content[0]:
                return message_content[0]["text"]
            else:
                 raise ImageError("Unexpected converse response format.")

        # Handle invoke_model response structure
        response_body_stream = response.get("body")
        if not response_body_stream:
             raise ImageError("Invalid response format: Missing body.")

        try:
            response_body = json.loads(response_body_stream.read())
        except Exception as e:
            raise ImageError(f"Error reading/decoding response body: {e}")

        if "images" in response_body and isinstance(response_body["images"], list) and len(response_body["images"]) > 0:
            try:
                return base64.b64decode(response_body.get("images")[0]) # Decode bytes directly
            except Exception as e:
                 raise ImageError(f"Error decoding base64 image: {e}")
        elif "error" in response_body:
             raise ImageError(f"Generation error: {response_body['error']}")

        raise ImageError("Unexpected invoke_model response format.")


def check_rate_limit(body):
    print(f"[{datetime.now()}] Checking rate limit...")
    try:
        body_dict = json.loads(body)
    except json.JSONDecodeError:
        raise ImageError("Invalid request format for rate limiting.")

    quality = body_dict.get('imageGenerationConfig', {}).get('quality', 'standard')

    # Use credentials from environment variables
    s3_aws_id = os.getenv('AMP_AWS_ID')
    s3_aws_secret = os.getenv('AMP_AWS_SECRET')
    if not s3_aws_id or not s3_aws_secret:
         raise ImageError("Missing AWS credentials for S3.")

    s3_client = boto3.client(
        service_name='s3',
        aws_access_key_id=s3_aws_id,
        aws_secret_access_key=s3_aws_secret,
        region_name=bucket_region
    )

    rate_data = {'premium': [], 'standard': []} # Default structure
    try:
        # Get current rate limit data
        print(f"[{datetime.now()}] Getting rate limit data from S3...")
        response = s3_client.get_object(
            Bucket=nova_image_bucket,
            Key='rate-limit/jsonData.json'
        )
        rate_data = json.loads(response['Body'].read().decode('utf-8'))
        print(f"[{datetime.now()}] Got rate limit data from S3.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            print(f"[{datetime.now()}] Rate limit file not found. Initializing.")
            rate_data = {'premium': [], 'standard': []}
        else:
            raise ImageError(f"Failed to check rate limit: {str(e)}")
    except Exception as e:
        print(f"[{datetime.now()}] Error getting/decoding rate limit data: {e}")
        rate_data = {'premium': [], 'standard': []} # Reset if corrupted or other error

    # Get current timestamp
    current_time = datetime.now().timestamp()
    # Keep only requests from last 20 minutes
    twenty_minutes_ago = current_time - 1200

    # Clean up old entries
    rate_data['premium'] = [t for t in rate_data.get('premium', []) if t > twenty_minutes_ago]
    rate_data['standard'] = [t for t in rate_data.get('standard', []) if t > twenty_minutes_ago]

    # Calculate the total count of requests in the last 20 minutes
    total_count = len(rate_data['premium']) * 2 + len(rate_data['standard'])

    # Check limits based on quality
    limit_exceeded = False
    if quality == 'premium':
        if total_count + 2 > rate_limit:
            limit_exceeded = True
        else:
            rate_data['premium'].append(current_time)
    else:  # standard
        if total_count + 1 > rate_limit:
            limit_exceeded = True
        else:
            rate_data['standard'].append(current_time)

    if limit_exceeded:
        print(f"[{datetime.now()}] Rate limit exceeded.")
        raise ImageError(rate_limit_message)

    # Update rate limit file
    try:
        print(f"[{datetime.now()}] Updating rate limit data in S3...")
        s3_client.put_object(
            Bucket=nova_image_bucket,
            Key='rate-limit/jsonData.json',
            Body=json.dumps(rate_data),
            ContentType='application/json'
        )
        print(f"[{datetime.now()}] Updated rate limit data in S3.")
    except Exception as e:
        print(f"[{datetime.now()}] Warning: Failed to update rate limit data in S3: {e}")
        # Decide if this should be fatal or just logged

    print(f"[{datetime.now()}] Rate limit check passed.")


def generate_image(body):
    """Generate image using Bedrock service."""
    start_time = datetime.now()
    print(f"[{start_time}] --- generate_image START ---")
    aws_id = os.getenv('AMP_AWS_ID') # Use specific credentials for this function
    aws_secret = os.getenv('AMP_AWS_SECRET')
    if not aws_id or not aws_secret:
        print(f"[{datetime.now()}] Missing AWS credentials for generate_image.")
        return "Configuration error: Missing AWS credentials." # Return error message

    try:
        check_rate_limit(body)

        client = BedrockClient(
            aws_id=aws_id,
            aws_secret=aws_secret,
            model_id='amazon.nova-canvas-v1:0'
        )

        result = client.generate_image(body)
        end_time = datetime.now()
        print(f"[{end_time}] --- generate_image END (Success). Duration: {end_time - start_time} ---")
        return result
    except ImageError as e:
        end_time = datetime.now()
        print(f"[{end_time}] --- generate_image END (ImageError: {e.message}). Duration: {end_time - start_time} ---")
        return e.message # Return the error message string
    except Exception as e:
        end_time = datetime.now()
        print(f"[{end_time}] --- generate_image END (Unexpected Error: {str(e)}). Duration: {end_time - start_time} ---")
        logging.exception("Unexpected error in generate_image function")
        return f"An unexpected error occurred: {str(e)}" # Return generic error


def generate_prompt(body):
    start_time = datetime.now()
    print(f"[{start_time}] --- generate_prompt START ---")
    aws_id = os.getenv('AMP_AWS_ID') # Use specific credentials
    aws_secret = os.getenv('AMP_AWS_SECRET')
    if not aws_id or not aws_secret:
        print(f"[{datetime.now()}] Missing AWS credentials for generate_prompt.")
        return "Configuration error: Missing AWS credentials."

    try:
        client = BedrockClient(
            aws_id=aws_id,
            aws_secret=aws_secret,
            # Ensure this model ID is correct for converse API
            model_id='anthropic.claude-3-sonnet-20240229-v1:0'
        )

        # Prepare messages for Claude 3 Sonnet converse API
        # Assuming 'body' contains the user's request for a prompt
        messages = [{"role": "user", "content": [{"type": "text", "text": body}]}] # Adjust based on actual input 'body'

        result = client.generate_prompt(messages) # Pass the prepared messages
        end_time = datetime.now()
        print(f"[{end_time}] --- generate_prompt END (Success). Duration: {end_time - start_time} ---")
        return result
    except ImageError as e:
        end_time = datetime.now()
        print(f"[{end_time}] --- generate_prompt END (ImageError: {e.message}). Duration: {end_time - start_time} ---")
        return f"Error generating prompt: {e.message}"
    except Exception as e:
        end_time = datetime.now()
        print(f"[{end_time}] --- generate_prompt END (Unexpected Error: {str(e)}). Duration: {end_time - start_time} ---")
        logging.exception("Unexpected error in generate_prompt function")
        return f"An unexpected error occurred while generating prompt: {str(e)}"