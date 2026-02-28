"""
utils/s3.py
TESTING 
Helpers for storing and retrieving zoning documents, public hearing transcripts,
and OCR/Comprehend outputs from AWS S3.

Set the following environment variables (or add them to .env):
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_REGION            (default: us-east-1)
  S3_BUCKET_NAME        (default: rootwatch-documents)

Quick credential test:
  GET /api/admin/aws-check   — returns JSON with ok, identity, and bucket status.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_BUCKET = os.environ.get("S3_BUCKET_NAME", "rootwatch-documents")
_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Lazy import so the app starts without boto3 if S3 is not needed
_s3_client = None


def _get_client():
    global _s3_client
    if _s3_client is None:
        try:
            import boto3
            _s3_client = boto3.client("s3", region_name=_REGION)
        except ImportError:
            raise RuntimeError(
                "boto3 is required for S3 operations. Install it with: pip install boto3"
            )
    return _s3_client


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def upload_document(
    file_bytes: bytes,
    key: str,
    content_type: str = "application/pdf",
    metadata: Optional[dict] = None,
) -> str:
    """
    Upload a document to S3.

    Args:
        file_bytes:    Raw file content.
        key:           S3 object key, e.g. "zoning/marion_county/dc_permit_2026.pdf"
        content_type:  MIME type.
        metadata:      Optional key-value metadata dict stored alongside the object.

    Returns:
        The S3 URI of the uploaded object: s3://<bucket>/<key>
    """
    client = _get_client()
    extra_args = {"ContentType": content_type}
    if metadata:
        extra_args["Metadata"] = {str(k): str(v) for k, v in metadata.items()}

    client.put_object(
        Bucket=_BUCKET,
        Key=key,
        Body=file_bytes,
        **extra_args,
    )
    logger.info(f"Uploaded s3://{_BUCKET}/{key}")
    return f"s3://{_BUCKET}/{key}"


# ---------------------------------------------------------------------------
# Pre-signed URLs (for secure frontend access)
# ---------------------------------------------------------------------------

def get_presigned_url(key: str, expiry_seconds: int = 3600) -> str:
    """
    Generate a pre-signed URL so the frontend can download a document
    directly from S3 without exposing credentials.

    Args:
        key:             S3 object key.
        expiry_seconds:  URL validity window (default 1 hour).

    Returns:
        HTTPS pre-signed URL string.
    """
    client = _get_client()
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _BUCKET, "Key": key},
        ExpiresIn=expiry_seconds,
    )
    return url


# ---------------------------------------------------------------------------
# List documents
# ---------------------------------------------------------------------------

def list_documents(prefix: str = "") -> list[dict]:
    """
    List all objects in the bucket under a given prefix.

    Returns a list of dicts with keys: key, size_bytes, last_modified.
    """
    client = _get_client()
    paginator = client.get_paginator("list_objects_v2")
    results = []
    for page in paginator.paginate(Bucket=_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            results.append(
                {
                    "key": obj["Key"],
                    "size_bytes": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                }
            )
    return results


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_document(key: str) -> None:
    """Remove an object from S3."""
    client = _get_client()
    client.delete_object(Bucket=_BUCKET, Key=key)
    logger.info(f"Deleted s3://{_BUCKET}/{key}")


# ---------------------------------------------------------------------------
# Credential / connectivity check
# ---------------------------------------------------------------------------

def verify_credentials() -> dict:
    """
    Validate that AWS credentials are configured and working.

    Checks (in order):
      1. boto3 is installed
      2. AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY are set
      3. STS GetCallerIdentity succeeds  (proves the keys are valid)
      4. S3 ListBucket on the configured bucket succeeds

    Returns a dict:
      ok          bool    True only if all checks pass
      identity    dict    AWS account/user info from STS (or None on failure)
      bucket      dict    Bucket check result
      errors      list    Any error messages
    """
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

    errors = []
    identity = None
    bucket_result = {"bucket": _BUCKET, "accessible": False, "detail": None}

    # 1. Check env vars are set
    key_id = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")

    if not key_id or key_id == "your_access_key_here":
        errors.append("AWS_ACCESS_KEY_ID is not set. Add it to your .env file.")
    if not secret or secret == "your_secret_key_here":
        errors.append("AWS_SECRET_ACCESS_KEY is not set. Add it to your .env file.")

    if errors:
        return {"ok": False, "identity": None, "bucket": bucket_result, "errors": errors}

    # 2. STS identity check
    try:
        sts = boto3.client(
            "sts",
            region_name=_REGION,
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
        )
        resp = sts.get_caller_identity()
        identity = {
            "account_id": resp["Account"],
            "user_arn":   resp["Arn"],
            "user_id":    resp["UserId"],
        }
    except NoCredentialsError:
        errors.append("Credentials not found by boto3. Check AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY.")
    except ClientError as e:
        errors.append(f"STS error: {e.response['Error']['Code']} – {e.response['Error']['Message']}")
    except (BotoCoreError, Exception) as e:
        errors.append(f"STS check failed: {str(e)}")

    if errors:
        return {"ok": False, "identity": identity, "bucket": bucket_result, "errors": errors}

    # 3. S3 bucket accessibility check
    try:
        s3 = boto3.client(
            "s3",
            region_name=_REGION,
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
        )
        # head_bucket is cheap — no data transferred, just checks access
        s3.head_bucket(Bucket=_BUCKET)
        bucket_result["accessible"] = True
        bucket_result["detail"] = f"Bucket '{_BUCKET}' exists and is accessible."
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "404":
            bucket_result["detail"] = (
                f"Bucket '{_BUCKET}' does not exist yet. "
                "Create it in the AWS console (region: " + _REGION + ")."
            )
        elif code in ("403", "AccessDenied"):
            bucket_result["detail"] = (
                f"Bucket '{_BUCKET}' exists but your IAM user lacks s3:ListBucket permission."
            )
        else:
            bucket_result["detail"] = f"S3 error {code}: {e.response['Error']['Message']}"
        errors.append(bucket_result["detail"])
    except (BotoCoreError, Exception) as e:
        bucket_result["detail"] = f"S3 check failed: {str(e)}"
        errors.append(bucket_result["detail"])

    return {
        "ok": len(errors) == 0,
        "region": _REGION,
        "identity": identity,
        "bucket": bucket_result,
        "errors": errors,
    }
