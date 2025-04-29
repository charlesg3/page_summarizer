import json
import logging
import os
import uuid
import hashlib
from pathlib import Path
import time
import boto3
from typing import Dict, Any, Optional
import trafilatura
import requests
from urllib.parse import urlparse

# Import the summarizer
from summarizer import summarize_text, chunk_text

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 client
s3 = boto3.client('s3')


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


def extract_webpage_content(url: str, html_content: Optional[str] = None, include_comments: bool = False) -> Dict[str, Any]:
    """
    Extract content from a webpage using Trafilatura.
    
    Args:
        url: URL of the webpage
        html_content: Optional HTML content if already available
        include_comments: Whether to include comments in the extraction
        
    Returns:
        Dictionary with extraction results
    """
    try:
        # If HTML content is provided, use it directly
        if html_content:
            logger.info(f"Using provided HTML content for extraction")
            downloaded = html_content
        else:
            # Otherwise download the content from the URL
            logger.info(f"Downloading content from URL: {url}")
            downloaded = trafilatura.fetch_url(url)
            
        if not downloaded:
            return {
                "success": False,
                "message": "Failed to download webpage content"
            }
        
        # Extract the main content
        try:
            extracted_text = trafilatura.extract(
                downloaded,
                output_format="txt",  # Changed from "text" to "txt" to match valid formats
                include_comments=include_comments,
                include_tables=True,
                include_links=False,
                include_images=False,
                no_fallback=False
            )
            logger.info("Successfully extracted content with trafilatura")
        except Exception as e:
            logger.error(f"Error in trafilatura extraction: {str(e)}")
            extracted_text = None
        
        if not extracted_text:
            # Try with fallback extraction
            logger.info("Primary extraction failed, trying with fallback")
            try:
                extracted_text = trafilatura.extract(
                    downloaded,
                    output_format="txt",  # Changed from "text" to "txt" to match valid formats
                    include_comments=include_comments,
                    include_tables=True,
                    include_links=False,
                    include_images=False,
                    no_fallback=True
                )
            except Exception as e:
                logger.error(f"Error in fallback extraction: {str(e)}")
                extracted_text = None
            
        if not extracted_text:
            return {
                "success": False,
                "message": "Failed to extract content from webpage"
            }
        
        # Get metadata if available
        metadata = trafilatura.metadata.extract_metadata(downloaded, default_url=url)
        title = None
        if metadata:
            title = metadata.title
            
        # If no title from metadata, try to extract from URL
        if not title:
            parsed_url = urlparse(url)
            title = parsed_url.netloc + parsed_url.path
        
        return {
            "success": True,
            "message": "Content extracted successfully",
            "content": extracted_text,
            "title": title
        }
        
    except Exception as e:
        logger.error(f"Error extracting webpage content: {str(e)}")
        return {
            "success": False,
            "message": f"Error extracting webpage content: {str(e)}"
        }


def process_webpage(
    page_url: str, api_key: str, html_content: Optional[str] = None, model: str = "claude-3-haiku-20240307",
    include_comments: bool = False, mode: str = "default"
) -> Dict[str, Any]:
    """
    Process a webpage URL to extract content and summarize it.

    Args:
        page_url: Webpage URL
        api_key: Anthropic API key for summarization
        html_content: Optional HTML content if already available
        model: Claude model to use for summarization
        include_comments: Whether to include comments in the extraction
        mode: Summarization mode ("default" or "debate")

    Returns:
        Dictionary with results
    """
    # Generate a unique ID for this page
    page_id = generate_page_id(page_url)
    
    # Check if we already have a status file for this page
    status = check_status_file(page_id, mode)
    if status:
        # If the processing is complete, return the result
        if status.get('status') == 'completed' and status.get('summary'):
            return {
                "success": True,
                "message": "Summary retrieved from cache",
                "page_id": page_id,
                "page_url": page_url,
                "summary": status.get('summary'),
                "cached": True
            }
        # If processing is in progress, return the status
        elif status.get('status') == 'processing':
            return {
                "success": True,
                "message": "Processing in progress",
                "page_id": page_id,
                "page_url": page_url,
                "status": "processing",
                "cached": True
            }
    
    # Create a unique working directory in /tmp
    working_dir = f"/tmp/{uuid.uuid4()}"
    os.makedirs(working_dir, exist_ok=True)
    logger.info(f"Working directory: {working_dir}")

    # Update status to processing
    update_status_file(page_id, {
        "status": "processing",
        "page_id": page_id,
        "page_url": page_url,
        "message": "Started processing webpage"
    }, mode)

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

        result = {
            "success": True,
            "message": "Content extracted successfully",
            "page_id": page_id,
            "page_url": page_url,
            "status": "summarizing"
        }
        
        # Update status
        update_status_file(page_id, result, mode)

        # Summarize the extracted content
        logger.info("Summarizing extracted webpage content...")

        text_content = extraction_result["content"]
        text_length = len(text_content)

        # Process text in chunks if necessary
        if text_length <= 400000:  # Increased chunk size for Claude 3.7 Sonnet
            logger.info("Text is within Claude's context window for direct summarization")
            
            # Use different summarization approach based on mode
            if mode == "debate":
                logger.info(f"Debate mode: Analyzing content with length {len(text_content)}")
                # Use temperature 0 for debate mode
                summary = summarize_text(text_content, api_key, model=model, temperature=0, mode="debate", html_output=True)
            else:
                # Default mode uses standard summarization
                summary = summarize_text(text_content, api_key, model=model, mode="default", html_output=True)

            if summary:
                result["summary"] = summary
                result["status"] = "completed"
                result["success"] = True
                logger.info("Summarization completed successfully")
                update_status_file(page_id, result, mode)
            else:
                logger.error("Failed to summarize text")
                result["summary_error"] = "Failed to generate summary"
                result["status"] = "failed"
                result["success"] = False
                update_status_file(page_id, result, mode)
        else:
            logger.info(f"Text is too long. Breaking into chunks and summarizing each chunk.")

            # Split text into manageable chunks
            chunks = chunk_text(text_content)
            logger.info(f"Created {len(chunks)} chunks for processing")

            # Process each chunk
            all_summaries = []

            for i, chunk in enumerate(chunks, 1):
                logger.info(f"Summarizing chunk {i} of {len(chunks)}")
                
                # Update status
                result["status"] = f"summarizing_chunk_{i}_of_{len(chunks)}"
                update_status_file(page_id, result, mode)

                # For individual chunks, don't request HTML output
                if mode == "debate":
                    # For debate mode, use temperature 0 and critical analysis prompt for each chunk
                    chunk_summary = summarize_text(chunk, api_key, model=model, html_output=False, temperature=0, mode="debate")
                else:
                    # Default mode uses standard summarization
                    chunk_summary = summarize_text(chunk, api_key, model=model, html_output=False, mode="default")

                if chunk_summary is None:
                    logger.error(f"Failed to summarize chunk {i}")
                    continue

                logger.info(f"Chunk {i} summarized")
                all_summaries.append(f"--- Segment {i} ---\n\n{chunk_summary}")

            # If there are multiple chunks, create a summary of summaries
            if len(chunks) > 1:
                combined_summaries = "\n\n".join(all_summaries)
                
                # Update status
                result["status"] = "creating_meta_summary"
                update_status_file(page_id, result, mode)

                # For debate mode, just combine the individual chunk analyses without creating a meta-summary
                if mode == "debate":
                    logger.info("Debate mode: Combining individual chunk analyses without meta-summary")
                    
                    # Process each chunk with HTML output for debate mode
                    html_summaries = []
                    for i, chunk in enumerate(chunks, 1):
                        logger.info(f"Generating HTML output for chunk {i} in debate mode")
                        
                        # Use temperature 0 for debate mode and request HTML output
                        chunk_html = summarize_text(chunk, api_key, model=model, html_output=True, temperature=0, mode="debate")
                        
                        if chunk_html:
                            html_summaries.append(f"<h2>Segment {i} Analysis</h2>\n{chunk_html}")
                    
                    # Combine all HTML summaries
                    if html_summaries:
                        result["summary"] = "<div>\n" + "\n\n".join(html_summaries) + "\n</div>"
                    else:
                        result["summary"] = "<div><p>Failed to generate any analyses.</p></div>"
                
                # For default mode, proceed with meta-summary creation
                else:
                    # Check if combined summaries are still large
                    if len(combined_summaries) > 400000:
                        logger.info("Creating meta-summary of all chunk summaries")
                        meta_summary = summarize_text(combined_summaries, api_key, model=model, html_output=True)

                        if meta_summary is None:
                            logger.error("Failed to create meta-summary")
                            result["summary"] = "<div>" + combined_summaries.replace("\n", "<br>") + "</div>"
                        else:
                            result["summary"] = (
                                "<div><h1>Executive Summary</h1>" + meta_summary + 
                                "<h1>Detailed Summaries</h1>" + combined_summaries.replace("\n", "<br>") + "</div>"
                            )
                    else:
                        logger.info("Creating unified summary from all chunk summaries")
                        meta_prompt = f"""Below are summaries of different segments of a longer text. 
Please create one unified, coherent summary that incorporates the key points from all segments:

{combined_summaries}"""
                        meta_summary = summarize_text(meta_prompt, api_key, model=model, html_output=True)

                        if meta_summary is None:
                            logger.error("Failed to create unified summary")
                            result["summary"] = "<div>" + combined_summaries.replace("\n", "<br>") + "</div>"
                        else:
                            result["summary"] = (
                                "<div><h1>Executive Summary</h1>" + meta_summary + 
                                "<h1>Detailed Summaries</h1>" + combined_summaries.replace("\n", "<br>") + "</div>"
                            )
            else:
                # Only one chunk was processed
                result["summary"] = all_summaries[0] if all_summaries else "Failed to generate any summaries."
            
            # Update final status
            result["status"] = "completed"
            update_status_file(page_id, result, mode)

        return result
    except Exception as e:
        logger.error(f"Error processing webpage: {str(e)}")
        error_result = {
            "success": False, 
            "message": f"Error processing webpage: {str(e)}",
            "status": "failed",
            "page_id": page_id,
            "page_url": page_url
        }
        update_status_file(page_id, error_result, mode)
        return error_result
    finally:
        # List all files in working directory for debugging
        logger.info("Files in working directory:")
        for file in Path(working_dir).glob("*"):
            logger.info(f"- {file}")


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
        "mode": "default"                     # optional, can be "default" or "debate"
    }
    """
    # Log the full event for debugging
    logger.info("==== FULL EVENT START ====")
    logger.info(json.dumps(event, indent=2))
    logger.info("==== FULL EVENT END ====")

    # Set up environment
    if not setup_environment():
        return {"statusCode": 500, "body": json.dumps({"success": False, "message": "Failed to set up environment"})}

    # Parse the event
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

        result = process_webpage(page_url, api_key, html_content, model, include_comments, mode)

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
