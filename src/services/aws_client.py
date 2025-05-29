import boto3
import json
import base64
from typing import Optional, Dict, Any, List
from botocore.config import Config
from botocore.exceptions import ClientError
from src.models.config import config
from src.utils.logger import app_logger, log_performance
from src.utils.exceptions import BedrockError, ConfigurationError

class AWSClientManager:
    """Singleton pattern for AWS client management with connection pooling"""
    
    _instance = None
    _bedrock_client = None
    _s3_client = None
    _logs_client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            app_logger.info("Initializing AWS Client Manager")
    
    @property
    def bedrock_client(self):
        """Lazy initialization of Bedrock client with connection pooling"""
        if self._bedrock_client is None:
            try:
                self._bedrock_client = boto3.client(
                    service_name='bedrock-runtime',
                    aws_access_key_id=config.aws_access_key_id,
                    aws_secret_access_key=config.aws_secret_access_key,
                    region_name=config.aws_region,
                    config=Config(
                        read_timeout=config.bedrock_timeout,
                        max_pool_connections=10,
                        retries={'max_attempts': 3}
                    )
                )
                app_logger.info("Bedrock client initialized")
            except Exception as e:
                raise ConfigurationError(f"Failed to initialize Bedrock client: {str(e)}")
        return self._bedrock_client
    
    @property
    def s3_client(self):
        """Lazy initialization of S3 client"""
        if self._s3_client is None:
            try:
                self._s3_client = boto3.client(
                    service_name='s3',
                    aws_access_key_id=config.aws_access_key_id,
                    aws_secret_access_key=config.aws_secret_access_key,
                    region_name=config.bucket_region,
                    config=Config(max_pool_connections=5)
                )
                app_logger.info("S3 client initialized")
            except Exception as e:
                raise ConfigurationError(f"Failed to initialize S3 client: {str(e)}")
        return self._s3_client
    
    @property
    def logs_client(self):
        """Lazy initialization of CloudWatch Logs client"""
        if self._logs_client is None and config.is_lambda:
            try:
                self._logs_client = boto3.client(
                    service_name='logs',
                    aws_access_key_id=config.aws_access_key_id,
                    aws_secret_access_key=config.aws_secret_access_key,
                    region_name=config.aws_region
                )
                app_logger.info("CloudWatch Logs client initialized")
            except Exception as e:
                app_logger.warning(f"Failed to initialize CloudWatch Logs client: {str(e)}")
        return self._logs_client

class BedrockService:
    """Service class for AWS Bedrock operations"""
    
    def __init__(self):
        self.client_manager = AWSClientManager()
    
    @log_performance
    def generate_image(self, request_body: str) -> bytes:
        """Generate image using Bedrock Nova Canvas model"""
        try:
            app_logger.info("Calling Bedrock invoke_model for image generation")
            
            body_bytes = request_body.encode('utf-8') if isinstance(request_body, str) else request_body
            
            response = self.client_manager.bedrock_client.invoke_model(
                body=body_bytes,
                modelId=config.nova_canvas_model,
                accept="application/json",
                contentType="application/json"
            )
            
            image_data = self._process_image_response(response)
            
            # Store response asynchronously (fire and forget)
            self._store_response_async(request_body, image_data)
            
            return image_data
            
        except ClientError as e:
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            app_logger.error(f"Bedrock client error: {error_msg}")
            raise BedrockError(f"Image generation failed: {error_msg}")
        except Exception as e:
            app_logger.error(f"Unexpected error in image generation: {str(e)}")
            raise BedrockError(f"Unexpected error: {str(e)}")
    
    @log_performance
    def generate_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Generate text prompt using Bedrock Nova Lite model"""
        try:
            app_logger.info("Calling Bedrock converse for prompt generation")
            
            response = self.client_manager.bedrock_client.converse(
                modelId=config.nova_lite_model,
                messages=messages
            )
            
            return self._process_text_response(response)
            
        except ClientError as e:
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            app_logger.error(f"Bedrock client error: {error_msg}")
            raise BedrockError(f"Prompt generation failed: {error_msg}")
        except Exception as e:
            app_logger.error(f"Unexpected error in prompt generation: {str(e)}")
            raise BedrockError(f"Unexpected error: {str(e)}")
    
    def _process_image_response(self, response) -> bytes:
        """Process Bedrock image response"""
        try:
            response_body_stream = response.get("body")
            if not response_body_stream:
                raise BedrockError("Invalid response format: Missing body")
            
            response_body = json.loads(response_body_stream.read())
            app_logger.debug(f"Bedrock response keys: {list(response_body.keys())}")
            
            if "images" in response_body and isinstance(response_body["images"], list) and len(response_body["images"]) > 0:
                image_b64 = response_body["images"][0]
                app_logger.debug(f"Base64 image length: {len(image_b64)} characters")
                
                # Decode base64 to bytes
                image_bytes = base64.b64decode(image_b64)
                app_logger.info(f"Decoded image to {len(image_bytes)} bytes")
                
                return image_bytes
            elif "error" in response_body:
                raise BedrockError(f"Generation error: {response_body['error']}")
            else:
                raise BedrockError("Unexpected response format")
                
        except json.JSONDecodeError as e:
            raise BedrockError(f"Error decoding response: {str(e)}")
        except Exception as e:
            raise BedrockError(f"Error processing image response: {str(e)}")
    
    def _process_text_response(self, response) -> str:
        """Process Bedrock text response"""
        try:
            if "output" in response and "message" in response["output"]:
                message_content = response["output"]["message"]["content"]
                if (message_content and isinstance(message_content, list) and 
                    len(message_content) > 0 and "text" in message_content[0]):
                    return message_content[0]["text"]
            
            raise BedrockError("Unexpected converse response format")
            
        except Exception as e:
            raise BedrockError(f"Error processing text response: {str(e)}")
    
    def _store_response_async(self, request_body: str, image_data: bytes):
        """Store response to S3 asynchronously (non-blocking)"""
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            
            # Store response body
            response_key = f'responses/{timestamp}_response.json'
            self.client_manager.s3_client.put_object(
                Bucket=config.nova_image_bucket,
                Key=response_key,
                Body=request_body,
                ContentType='application/json'
            )
            
            # Store image if present
            if image_data:
                image_key = f'images/{timestamp}_image.png'
                self.client_manager.s3_client.put_object(
                    Bucket=config.nova_image_bucket,
                    Key=image_key,
                    Body=image_data,
                    ContentType='image/png'
                )
            
            app_logger.debug(f"Stored response and image to S3: {timestamp}")
            
        except Exception as e:
            # Don't fail the main operation if storage fails
            app_logger.warning(f"Failed to store response to S3: {str(e)}")

# Global service instance
bedrock_service = BedrockService()