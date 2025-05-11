import json
import logging
import os
import uuid
import hashlib
import time
import boto3
from typing import Dict, Any, Optional

# Import local modules
from content_extractor import extract_webpage_content
from webpage_processor import process_summary_job

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3 = boto3.client('s3')
lambda_client = boto3.client('lambda')


def setup_environment():
    """Setup environment for webpage processing"""
    logger.info("Setting up environment variables")
    # Add the layer binaries to PATH if needed
    os.environ["PATH"] = f"/opt/bin:{os.environ.get('PATH', '')}"
    # Add the layer libraries to LD_LIBRARY_PATH if needed
    os.environ["LD_LIBRARY_PATH"] = f"/opt/lib:{os.environ.get('LD_LIBRARY_PATH', '')}"

    # Make sure we can import trafilatura
    try:
        import trafilatura
        logger.info(f"Trafilatura version: {trafilatura.__version__}")
        return True
    except Exception as e:
        logger.error(f"Failed to verify tools: {str(e)}")
        return False


def generate_page_id(url: str) -> str:
    """
    Generate a unique ID for a webpage URL.
    
    Args:
        url: Webpage URL
        
    Returns:
        A unique ID based on the URL
    """
    # Create a hash of the URL to use as ID
    return hashlib.md5(url.encode('utf-8')).hexdigest()


def check_status_file(page_id: str, mode: str = "default") -> Dict[str, Any]:
    """
    Check if a status file exists for the given page ID and mode.
    
    Args:
        page_id: Unique page identifier
        mode: Mode of operation ("default" or "debate")
        
    Returns:
        Status information if file exists, None otherwise
    """
    bucket = os.environ.get("BUCKET")
    # Use different paths for different modes
    if mode == "debate":
        status_key = f"analysis/{page_id}.json"
    else:
        status_key = f"summaries/{page_id}.json"
    
    try:
        response = s3.get_object(Bucket=bucket, Key=status_key)
        status_data = json.loads(response['Body'].read().decode('utf-8'))
        logger.info(f"Found existing status file for page {page_id} in mode {mode}")
        
        # If status is completed and we have an s3_path, generate a fresh presigned URL
        if status_data.get("status") == "completed" and status_data.get("s3_path"):
            # Extract the object key from the s3_path
            s3_path = status_data["s3_path"]
            if s3_path.startswith(f"s3://{bucket}/"):
                object_key = s3_path[len(f"s3://{bucket}/"):]
                # Generate a fresh presigned URL
                presigned_url = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket, 'Key': object_key},
                    ExpiresIn=604800  # 7 days
                )
                status_data["presigned_url"] = presigned_url
                logger.info(f"Generated fresh presigned URL for {page_id}")
        
        return status_data
    except Exception as e:
        logger.info(f"No status file found for page {page_id} in mode {mode}: {str(e)}")
        return None


def update_status_file(page_id: str, status: Dict[str, Any], mode: str = "default") -> bool:
    """
    Create or update the status file for a webpage.
    
    Args:
        page_id: Unique page identifier
        status: Status information to store
        mode: Mode of operation ("default" or "debate")
        
    Returns:
        True if successful, False otherwise
    """
    bucket = os.environ.get("BUCKET")
    # Use different paths for different modes
    if mode == "debate":
        status_key = f"analysis/{page_id}.json"
    else:
        status_key = f"summaries/{page_id}.json"
    
    try:
        status['last_updated'] = time.time()
        s3.put_object(
            Bucket=bucket,
            Key=status_key,
            Body=json.dumps(status),
            ContentType='application/json'
        )
        logger.info(f"Updated status file for page {page_id} in mode {mode}")
        return True
    except Exception as e:
        logger.error(f"Failed to update status file: {str(e)}")
        return False


def start_async_processing(page_url: str, api_key: str, html_content: Optional[str] = None, 
                          model: str = "claude-3-7-sonnet-latest", include_comments: bool = False, 
                          mode: str = "default", context=None) -> Dict[str, Any]:
    """
    Start asynchronous processing of a webpage.
    
    Args:
        page_url: Webpage URL
        api_key: Anthropic API key for summarization
        html_content: Optional HTML content if already available
        model: Claude model to use for summarization
        include_comments: Whether to include comments in the extraction
        mode: Summarization mode ("default" or "debate")
        context: Lambda context object
        
    Returns:
        Dictionary with initial status
    """
    # Generate a unique ID for this page
    page_id = generate_page_id(page_url)
    
    # Initialize status
    status = {
        "status": "processing",
        "page_id": page_id,
        "page_url": page_url,
        "message": "Started processing webpage"
    }
    
    # Update status file
    update_status_file(page_id, status, mode)
    
    # Extract content first to reduce the payload size for the async Lambda call
    try:
        # Extract webpage content
        extraction_result = extract_webpage_content(page_url, html_content, include_comments)
        
        if not extraction_result["success"]:
            error_status = {
                "status": "failed",
                "page_id": page_id,
                "page_url": page_url,
                "message": extraction_result["message"]
            }
            update_status_file(page_id, error_status, mode)
            return error_status
            
        # Update status to indicate content extraction is complete
        status["message"] = "Content extracted, starting summarization"
        status["status"] = "summarizing"
        update_status_file(page_id, status, mode)
        
        # Prepare payload for async processing
        payload = {
            "page_id": page_id,
            "page_url": page_url,
            "api_key": api_key,
            "model": model,
            "mode": mode,
            "extracted_content": extraction_result["content"],
            "page_title": extraction_result.get("title"),
            "is_async_job": True
        }
        
        # Invoke Lambda function asynchronously
        function_name = context.function_name if context else os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        logger.info(f"Invoking Lambda function {function_name} asynchronously")
        
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='Event',  # Asynchronous invocation
            Payload=json.dumps(payload)
        )
        
        logger.info(f"Async Lambda invocation response: {response}")
        
        # Return the current status
        return {
            "success": True,
            "message": "Processing started asynchronously",
            "page_id": page_id,
            "page_url": page_url,
            "status": "summarizing"
        }
        
    except Exception as e:
        logger.error(f"Error starting async processing: {str(e)}")
        error_status = {
            "success": False,
            "message": f"Error starting async processing: {str(e)}",
            "status": "failed",
            "page_id": page_id,
            "page_url": page_url
        }
        update_status_file(page_id, error_status, mode)
        return error_status


def lambda_handler(event, context):
    """
    Lambda entry point

    Expected event format:
    {
        "page_url": "https://example.com/page",
        "html_content": "<html>...</html>",  # optional
        "api_key": "your_anthropic_api_key",  # required for summarization
        "model": "claude-3-haiku-20240307",   # optional
        "include_comments": false,            # optional
        "mode": "default",                    # optional, can be "default" or "debate"
        "is_async_job": false                 # optional, set to true for async processing jobs
    }
    """
    # Log the event (excluding sensitive data)
    logger.info("==== EVENT INFO ====")
    safe_event = {k: "***" if k in ["api_key", "html_content", "extracted_content"] else v for k, v in event.items()}
    logger.info(json.dumps(safe_event, indent=2))
    
    # Set up environment
    if not setup_environment():
        return {"statusCode": 500, "body": json.dumps({"success": False, "message": "Failed to set up environment"})}

    # Check if this is an async processing job
    if event.get("is_async_job", False):
        logger.info("Processing async job")
        
        # Extract parameters
        page_id = event.get("page_id")
        page_url = event.get("page_url")
        api_key = event.get("api_key")
        model = event.get("model", "claude-3-7-sonnet-latest")
        mode = event.get("mode", "default")
        extracted_content = event.get("extracted_content")
        page_title = event.get("page_title")
        
        # Process the summary
        result = process_summary_job(
            page_id=page_id,
            page_url=page_url,
            text_content=extracted_content,
            api_key=api_key,
            model=model,
            mode=mode,
            page_title=page_title,
            update_status_callback=lambda pid, status, m: update_status_file(pid, status, m)
        )
        
        return result

    # Parse the event for API Gateway requests
    if "body" in event:
        try:
            body = json.loads(event["body"])
            event.update(body)
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                    "Access-Control-Allow-Methods": "OPTIONS,POST,GET,PUT,DELETE",
                },
                "body": json.dumps({"success": False, "message": "Invalid JSON in request body"}),
            }

    # Check for page_url parameter (required)
    if "page_url" in event:
        page_url = event["page_url"]
        api_key = event.get("api_key")
        model = event.get("model", "claude-3-7-sonnet-latest")
        html_content = event.get("html_content")
        include_comments = event.get("include_comments", False)
        mode = event.get("mode", "default")
        
        # Generate page ID to check for existing status
        page_id = generate_page_id(page_url)
            
        # Check if we already have a status file for this page
        status = check_status_file(page_id, mode)
        if status:
            # Always return the current status, regardless of its state
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                    "Access-Control-Allow-Methods": "OPTIONS,POST,GET,PUT,DELETE",
                },
                "body": json.dumps(status),
            }

        # Check if API key is provided
        if not api_key:
            return {
                "statusCode": 400,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                    "Access-Control-Allow-Methods": "OPTIONS,POST,GET,PUT,DELETE",
                },
                "body": json.dumps({"success": False, "message": "API key required for summarization"}),
            }

        # Start asynchronous processing
        result = start_async_processing(page_url, api_key, html_content, model, include_comments, mode, context)

        return {
            "statusCode": 200 if result["success"] else 500,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET,PUT,DELETE",
            },
            "body": json.dumps(result),
        }
    else:
        return {
            "statusCode": 400,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET,PUT,DELETE",
            },
            "body": json.dumps({"success": False, "message": "Missing required parameter: page_url"}),
        }
