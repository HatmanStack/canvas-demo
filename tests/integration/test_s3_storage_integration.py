"""Integration tests for S3 storage operations against MiniStack."""

import json

import pytest

pytestmark = pytest.mark.integration


class TestS3StorageIntegration:
    """S3 storage integration tests."""

    def test_store_response_creates_objects(self, s3_client, s3_bucket):
        """Storing a response creates objects under responses/ and images/ prefixes."""
        timestamp = "20250101_120000_000000"
        response_key = f"responses/{timestamp}_response.json"
        image_key = f"images/{timestamp}_image.png"

        request_body = json.dumps({"taskType": "TEXT_IMAGE", "text": "test"})
        image_data = b"fake-png-data"

        s3_client.put_object(
            Bucket=s3_bucket,
            Key=response_key,
            Body=request_body,
            ContentType="application/json",
        )
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=image_key,
            Body=image_data,
            ContentType="image/png",
        )

        # Verify both objects exist and are retrievable
        resp_obj = s3_client.get_object(Bucket=s3_bucket, Key=response_key)
        assert resp_obj["ContentType"] == "application/json"

        img_obj = s3_client.get_object(Bucket=s3_bucket, Key=image_key)
        assert img_obj["Body"].read() == image_data

        # Cleanup
        s3_client.delete_object(Bucket=s3_bucket, Key=response_key)
        s3_client.delete_object(Bucket=s3_bucket, Key=image_key)

    def test_stored_json_is_valid(self, s3_client, s3_bucket):
        """Stored JSON is valid and retrievable."""
        key = "responses/test_valid_json.json"
        data = {"taskType": "INPAINTING", "params": {"text": "hello"}}

        s3_client.put_object(
            Bucket=s3_bucket,
            Key=key,
            Body=json.dumps(data),
            ContentType="application/json",
        )

        response = s3_client.get_object(Bucket=s3_bucket, Key=key)
        stored = json.loads(response["Body"].read().decode())

        assert stored["taskType"] == "INPAINTING"
        assert stored["params"]["text"] == "hello"

        # Cleanup
        s3_client.delete_object(Bucket=s3_bucket, Key=key)
