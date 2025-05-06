"""
Module for processing webpages and generating summaries.
Contains the core logic for summarizing webpage content.
"""

import json
import logging
import os
import uuid
from pathlib import Path
import time
from typing import Dict, Any, List

# Import the summarizer
from summarizer import summarize_text, chunk_text

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def process_summary_job(
    page_id: str,
    page_url: str,
    text_content: str,
    api_key: str,
    model: str = "claude-3-7-sonnet-latest",
    mode: str = "default",
    update_status_callback=None
) -> Dict[str, Any]:
    """
    Process a webpage content and generate a summary.
    
    Args:
        page_id: Unique identifier for the page
        page_url: URL of the webpage
        text_content: Extracted text content to summarize
        api_key: Anthropic API key for summarization
        model: Claude model to use for summarization
        mode: Summarization mode ("default" or "debate")
        update_status_callback: Function to call to update status
        
    Returns:
        Dictionary with results
    """
    # Create a unique working directory in /tmp
    working_dir = f"/tmp/{uuid.uuid4()}"
    os.makedirs(working_dir, exist_ok=True)
    logger.info(f"Working directory: {working_dir}")

    try:
        result = {
            "success": True,
            "page_id": page_id,
            "page_url": page_url,
        }

        # Process text based on length
        text_length = len(text_content)
        
        if text_length <= 400000:  # Increased chunk size for Claude 3.7 Sonnet
            # Process single chunk
            summary = process_single_chunk(text_content, api_key, model, mode)
            
            if summary:
                result["summary"] = summary
                result["status"] = "completed"
                result["success"] = True
                logger.info("Summarization completed successfully")
            else:
                logger.error("Failed to summarize text")
                result["summary_error"] = "Failed to generate summary"
                result["status"] = "failed"
                result["success"] = False
        else:
            # Process multiple chunks
            result = process_multiple_chunks(
                text_content, 
                page_id, 
                page_url, 
                api_key, 
                model, 
                mode, 
                update_status_callback
            )
        
        # Update final status if callback provided
        if update_status_callback:
            update_status_callback(page_id, result, mode)
            
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
        
        # Update error status if callback provided
        if update_status_callback:
            update_status_callback(page_id, error_result, mode)
            
        return error_result
    finally:
        # List all files in working directory for debugging
        logger.info("Files in working directory:")
        for file in Path(working_dir).glob("*"):
            logger.info(f"- {file}")


def process_single_chunk(text_content: str, api_key: str, model: str, mode: str) -> str:
    """
    Process a single chunk of text for summarization.
    
    Args:
        text_content: Text to summarize
        api_key: Anthropic API key
        model: Claude model to use
        mode: Summarization mode
        
    Returns:
        Summary text or None if failed
    """
    logger.info("Text is within Claude's context window for direct summarization")
    
    # Use different summarization approach based on mode
    if mode == "debate":
        logger.info(f"Debate mode: Analyzing content with length {len(text_content)}")
        # Use temperature 0 for debate mode
        return summarize_text(text_content, api_key, model=model, temperature=0, mode="debate", html_output=True)
    else:
        # Default mode uses standard summarization
        return summarize_text(text_content, api_key, model=model, mode="default", html_output=True)


def process_multiple_chunks(
    text_content: str, 
    page_id: str, 
    page_url: str, 
    api_key: str, 
    model: str, 
    mode: str,
    update_status_callback=None
) -> Dict[str, Any]:
    """
    Process text by breaking it into chunks and summarizing each chunk.
    
    Args:
        text_content: Text to summarize
        page_id: Unique identifier for the page
        page_url: URL of the webpage
        api_key: Anthropic API key
        model: Claude model to use
        mode: Summarization mode
        update_status_callback: Function to call to update status
        
    Returns:
        Dictionary with results
    """
    logger.info(f"Text is too long. Breaking into chunks and summarizing each chunk.")
    
    result = {
        "success": True,
        "page_id": page_id,
        "page_url": page_url,
    }

    # Split text into manageable chunks
    chunks = chunk_text(text_content)
    logger.info(f"Created {len(chunks)} chunks for processing")

    # Process each chunk
    all_summaries = []

    for i, chunk in enumerate(chunks, 1):
        logger.info(f"Summarizing chunk {i} of {len(chunks)}")
        
        # Update status
        if update_status_callback:
            result["status"] = f"summarizing_chunk_{i}_of_{len(chunks)}"
            update_status_callback(page_id, result, mode)

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
        if update_status_callback:
            result["status"] = "creating_meta_summary"
            update_status_callback(page_id, result, mode)

        # For debate mode, just combine the individual chunk analyses without creating a meta-summary
        if mode == "debate":
            result["summary"] = process_debate_mode_chunks(chunks, api_key, model)
        else:
            # For default mode, proceed with meta-summary creation
            result["summary"] = process_default_mode_chunks(combined_summaries, api_key, model, all_summaries)
    else:
        # Only one chunk was processed
        result["summary"] = all_summaries[0] if all_summaries else "Failed to generate any summaries."
    
    # Update final status
    result["status"] = "completed"
    return result


def process_debate_mode_chunks(chunks: List[str], api_key: str, model: str) -> str:
    """
    Process chunks in debate mode.
    
    Args:
        chunks: List of text chunks
        api_key: Anthropic API key
        model: Claude model to use
        
    Returns:
        HTML formatted summary
    """
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
        return "<div>\n" + "\n\n".join(html_summaries) + "\n</div>"
    else:
        return "<div><p>Failed to generate any analyses.</p></div>"


def process_default_mode_chunks(combined_summaries: str, api_key: str, model: str, all_summaries: List[str]) -> str:
    """
    Process chunks in default mode.
    
    Args:
        combined_summaries: All summaries combined into one string
        api_key: Anthropic API key
        model: Claude model to use
        all_summaries: List of individual summaries
        
    Returns:
        HTML formatted summary
    """
    # Check if combined summaries are still large
    if len(combined_summaries) > 400000:
        logger.info("Creating meta-summary of all chunk summaries")
        meta_summary = summarize_text(combined_summaries, api_key, model=model, html_output=True)

        if meta_summary is None:
            logger.error("Failed to create meta-summary")
            return "<div>" + combined_summaries.replace("\n", "<br>") + "</div>"
        else:
            return (
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
            return "<div>" + combined_summaries.replace("\n", "<br>") + "</div>"
        else:
            return (
                "<div><h1>Executive Summary</h1>" + meta_summary + 
                "<h1>Detailed Summaries</h1>" + combined_summaries.replace("\n", "<br>") + "</div>"
            )
