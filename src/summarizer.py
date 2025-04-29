#!/usr/bin/env python3

import os
import sys
import json
import time
import argparse
import requests
import anthropic
from pathlib import Path
from typing import List, Dict, Any, Optional


# ANSI color codes
class Colors:
    BLUE = "\033[0;34m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    RED = "\033[0;31m"
    CYAN = "\033[0;36m"
    BOLD = "\033[1m"
    NC = "\033[0m"  # No Color


def print_info(message: str) -> None:
    print(f"{Colors.BLUE}{Colors.BOLD}[INFO]{Colors.NC} {message}")


def print_success(message: str) -> None:
    print(f"{Colors.GREEN}{Colors.BOLD}[SUCCESS]{Colors.NC} {message}")


def print_warning(message: str) -> None:
    print(f"{Colors.YELLOW}{Colors.BOLD}[WARNING]{Colors.NC} {message}")


def print_error(message: str) -> None:
    print(f"{Colors.RED}{Colors.BOLD}[ERROR]{Colors.NC} {message}")


def print_header(message: str) -> None:
    print(f"\n{Colors.CYAN}{Colors.BOLD}==== {message} ===={Colors.NC}\n")


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Load configuration from a JSON file."""
    try:
        with open(config_path, "r") as file:
            config = json.load(file)

        # Validate config
        if not config.get("anthropic") or not config["anthropic"].get("api_key"):
            print_error(f"Invalid configuration in {config_path}.")
            print_info("Please ensure the file has the following format:")
            print(
                """{
  "anthropic": {
    "api_key": "YOUR_API_KEY_HERE"
  }
}"""
            )
            sys.exit(1)

        return config
    except FileNotFoundError:
        print_error(f"Configuration file not found: {config_path}")
        print_info("Please create a config.json file with the following format:")
        print(
            """{
  "anthropic": {
    "api_key": "YOUR_API_KEY_HERE"
  }
}"""
        )
        sys.exit(1)
    except json.JSONDecodeError:
        print_error(f"Invalid JSON in configuration file: {config_path}")
        sys.exit(1)


def summarize_text(
    text: str, api_key: str, model: str = "claude-3-7-sonnet-latest", max_retries: int = 3, html_output: bool = True,
    temperature: float = 0.5, mode: str = "default"
) -> Optional[str]:
    """Process text using Anthropic's Claude API.
    
    Args:
        text: Text to process
        api_key: Anthropic API key
        model: Claude model to use
        max_retries: Maximum number of retry attempts
        html_output: Whether to output HTML format
        temperature: Temperature for generation (0-1)
        mode: Processing mode ("default" for summarization, "debate" for critical analysis)
        
    Returns:
        Processed text as string or None if failed
    """

    client = anthropic.Anthropic(api_key=api_key)
    
    # Define mode-specific system prompts
    mode_instructions = {
        "default": """You are a helpful assistant that specializes in summarizing text. Your summaries cover all of the key points with examples. You provide the perspective of the author.

Please provide a summary of the text. Focus on the main points, key insights, and important details. The summary should be well-structured and capture the essence of the content. Provide the response from the perspective of the author and don't say the text says or the author says, state it from author's point of view.""",

        "debate": """You are an expert debate coach and critical thinker who specializes in analyzing arguments and identifying logical fallacies. You provide sharp, direct, and professional critical analysis.

Analyze the article or text and provide a critical analysis with counter-arguments following these steps:

1. Identify and summarize the main narrative, argument, or thesis being promoted (1–2 sentences maximum).

2. Detect any logical fallacies, weak reasoning, emotional manipulation, or unsupported assumptions. 
   - List each issue clearly.
   - Name the type of fallacy or tactic used.
   - Quote the part of the text where it happens (if possible).
   - Explain why it is logically weak.

3. Generate 2–3 strong, logically sound counter-arguments that challenge the author's position.
   - Use evidence, alternative perspectives, or common counterpoints.
   - Be rigorous and persuasive.
   - Assume the audience values clear thinking over emotional appeals.

Important:
- Be sharp, direct, and critical, but professional.
- Prioritize logical flaws over mere disagreement.
- Do not make up facts; base counters on reasoning or widely accepted information.
- DO NOT describe what you would do - actually perform the analysis.""",

        "debate_html": """You are an expert debate coach and critical thinker who specializes in analyzing arguments and identifying logical fallacies. You provide sharp, direct, and professional critical analysis.

Analyze the article or text and provide a critical analysis with counter-arguments following these steps:

1. Identify and summarize the main narrative, argument, or thesis being promoted (1–2 sentences maximum).

2. Detect any logical fallacies, weak reasoning, emotional manipulation, or unsupported assumptions. 
   - List each issue clearly.
   - Name the type of fallacy or tactic used.
   - Quote the part of the text where it happens (if possible).
   - Explain why it is logically weak.

3. Generate 2–3 strong, logically sound counter-arguments that challenge the author's position.
   - Use evidence, alternative perspectives, or common counterpoints.
   - Be rigorous and persuasive.
   - Assume the audience values clear thinking over emotional appeals.

Important:
- Be sharp, direct, and critical, but professional.
- Prioritize logical flaws over mere disagreement.
- Do not make up facts; base counters on reasoning or widely accepted information.
- DO NOT describe what you would do - actually perform the analysis.

Format your analysis in HTML without a preamble. Don't include the <html>, <head> or <style> tags. Start with a <div> and use the following structure:

<div>
  <h2>Narrative</h2>
  <p>[1-2 sentence summary of the main argument]</p>

  <h2>Logical Issues</h2>
  <ul>
    <li><strong>[fallacy type]</strong>: "[quote]" - [explanation]</li>
    <li><strong>[fallacy type]</strong>: "[quote]" - [explanation]</li>
  </ul>

  <h2>Counter-Arguments</h2>
  <ul>
    <li>[counter-argument 1]</li>
    <li>[counter-argument 2]</li>
    <li>[counter-argument 3]</li>
  </ul>
</div>"""
    }
    
    # Get the appropriate system prompt based on mode
    if mode == "debate" and html_output:
        system_prompt = mode_instructions["debate_html"]
    else:
        system_prompt = mode_instructions[mode]
    
    # Add HTML output instruction if needed
    if html_output and mode == "default":
        system_prompt += " Output in html without a preamble. Don't include the <html>, <head> or <style> tags. Start with a <div>."

    # User prompt contains only the text to process
    user_prompt = text

    for attempt in range(max_retries):
        try:
            print_info(f"API request attempt {attempt + 1} of {max_retries}")

            # Use streaming for long-running requests
            with client.messages.stream(
                model=model,
                max_tokens=32000,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            ) as stream:
                # Initialize an empty string to collect the response
                full_response = ""
                
                # Process each chunk as it arrives
                for chunk in stream:
                    if chunk.type == "content_block_delta":
                        if hasattr(chunk.delta, "text"):
                            full_response += chunk.delta.text
                
                # Return the complete response
                return full_response.strip()

        except anthropic.RateLimitError:
            print_warning("Rate limit reached. Waiting 60 seconds before retry...")
            time.sleep(60)

        except anthropic.APITimeoutError:
            print_warning("API request timed out. Retrying...")
            time.sleep(5)

        except Exception as e:
            print_warning(f"Error: {str(e)}")
            time.sleep(5)

    print_error(f"All API requests failed after {max_retries} attempts.")
    return None


def chunk_text(text: str, max_chunk_size: int = 400000, overlap: int = 8000) -> List[str]:
    """Split text into overlapping chunks of specified maximum size."""
    chunks = []
    start_pos = 0
    text_length = len(text)

    while start_pos < text_length:
        print_info(f"Chunk: {len(chunks)}")
        end_pos = start_pos + max_chunk_size

        if end_pos >= text_length:
            end_pos = text_length
        else:
            # Try to find a good break point (sentence or paragraph)
            for marker in ["\n\n", ".\n", ". ", "! ", "? "]:
                last_marker = text.rfind(marker, start_pos, end_pos)
                if last_marker != -1 and last_marker > start_pos + max_chunk_size // 2:
                    end_pos = last_marker + len(marker)
                    break

        chunks.append(text[start_pos:end_pos])
        start_pos = end_pos - overlap

        # Make sure we don't get stuck in a loop
        if start_pos >= text_length:
            break

    return chunks


def main():
    parser = argparse.ArgumentParser(description="Summarize text file using Claude API.")
    parser.add_argument("file", help="Text file to summarize")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    parser.add_argument(
        "--model",
        default="claude-3-7-sonnet-20250219",
        choices=["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
        help="Claude model to use",
    )
    parser.add_argument("--chunk-size", type=int, default=90000, help="Maximum characters per chunk")
    parser.add_argument("--chunk-overlap", type=int, default=2000, help="Character overlap between chunks")

    args = parser.parse_args()

    # Check if file exists
    file_path = Path(args.file)
    if not file_path.exists():
        print_error(f"File not found: {args.file}")
        sys.exit(1)

    # Load configuration
    config = load_config(args.config)
    api_key = config["anthropic"]["api_key"]

    print_header("Processing Text for Summarization")

    # Read the file
    with open(file_path, "r", encoding="utf-8") as file:
        text_content = file.read()

    text_length = len(text_content)
    print_info(f"Text length: {text_length} characters")
    print_info(f"Using Claude model: {args.model}")

    # Create output file name
    output_file = file_path.with_name(f"{file_path.stem}_summary.txt")

    # Process text in chunks if necessary
    if text_length <= args.chunk_size:
        print_info("Text is within Claude's context window for direct summarization")

        print_header("Summarizing Full Text")
        summary = summarize_text(text_content, api_key, model=args.model)

        if summary is None:
            print_error("Failed to summarize text.")
            sys.exit(1)

        with open(output_file, "w", encoding="utf-8") as file:
            file.write(summary)
    else:
        print_info(f"Text is too long. Breaking into chunks and summarizing each chunk.")

        # Split text into manageable chunks
        chunks = chunk_text(text_content, max_chunk_size=args.chunk_size, overlap=args.chunk_overlap)
        print_info(f"Created {len(chunks)} chunks for processing")

        # Process each chunk
        all_summaries = []

        for i, chunk in enumerate(chunks, 1):
            print_header(f"Summarizing Chunk {i} of {len(chunks)}")

            chunk_summary = summarize_text(chunk, api_key, model=args.model)

            if chunk_summary is None:
                print_error(f"Failed to summarize chunk {i}.")
                continue

            print_success(f"Chunk {i} summarized")
            all_summaries.append(f"--- Segment {i} ---\n\n{chunk_summary}")

        # If there are multiple chunks, create a summary of summaries
        if len(chunks) > 1:
            combined_summaries = "\n\n".join(all_summaries)

            # Check if combined summaries are still large
            if len(combined_summaries) > args.chunk_size:
                print_header("Creating Final Combined Summary")
                print_info(f"Combined summaries are still large. Creating a meta-summary.")

                meta_summary = summarize_text(combined_summaries, api_key, model=args.model)

                if meta_summary is None:
                    print_error("Failed to create meta-summary.")
                    final_output = combined_summaries
                else:
                    final_output = (
                        f"# Executive Summary\n\n{meta_summary}\n\n# Detailed Summaries\n\n{combined_summaries}"
                    )
            else:
                print_header("Creating Final Combined Summary")
                meta_prompt = f"""Below are summaries of different segments of a longer text. 
Please create one unified, coherent summary that incorporates the key points from all segments:

{combined_summaries}"""

                meta_summary = summarize_text(meta_prompt, api_key, model=args.model)

                if meta_summary is None:
                    print_error("Failed to create unified summary.")
                    final_output = combined_summaries
                else:
                    final_output = (
                        f"# Executive Summary\n\n{meta_summary}\n\n# Detailed Summaries\n\n{combined_summaries}"
                    )
        else:
            # Only one chunk was processed
            final_output = all_summaries[0] if all_summaries else "Failed to generate any summaries."

        with open(output_file, "w", encoding="utf-8") as file:
            file.write(final_output)

    print_header("Summary Complete")
    print_success(f"Summary saved to: {output_file}")

    # Display the first part of the summary
    print_header("Summary Preview")
    with open(output_file, "r", encoding="utf-8") as file:
        preview_lines = [next(file, None) for _ in range(20)]
        preview_text = "".join([line for line in preview_lines if line is not None])
        print(preview_text, end="")

    if len(preview_lines) == 20:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}... (summary continues) ...{Colors.NC}")

    print_success("Process completed successfully!")


if __name__ == "__main__":
    main()
