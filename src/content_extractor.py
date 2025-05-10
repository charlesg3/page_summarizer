"""
Module for extracting content from webpages.
Handles the extraction of main content from HTML using Trafilatura.
"""

import logging
from typing import Dict, Any, Optional
import trafilatura
from urllib.parse import urlparse

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
