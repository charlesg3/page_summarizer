# 📄 Page Summarizer

A powerful browser extension and AWS serverless application that summarizes web pages using AI.

## 🌟 Features

- **Web Page Summarization**: Extract and summarize content from any web page
- **AI-Powered Analysis**: Uses Claude AI models for high-quality summaries
- **Two Summary Modes**:
  - 📝 **Standard Summary**: Concise overview of the page content
  - 🔍 **Critical Analysis**: Identifies logical fallacies and provides counter-arguments
- **Comment Inclusion**: Option to include or exclude comments in the analysis
- **Serverless Architecture**: AWS Lambda-based backend for scalable processing
- **Secure Access**: Basic authentication for API access

## 🛠️ Architecture

The project consists of two main components:

### 1. Chrome Extension

- Extracts HTML content from the current page
- Sends content to the backend API for processing
- Displays the summary in a clean, readable format
- Configurable settings for API access and summary preferences

### 2. AWS Backend

- **API Gateway**: Secure endpoint with Basic Auth
- **Lambda Function**: Processes web page content using Trafilatura and Claude AI
- **S3 Storage**: Caches summaries for faster retrieval
- **CloudFormation**: Infrastructure as code for easy deployment

## 🚀 Installation

### Chrome Extension

1. Clone this repository
2. Open Chrome and navigate to `chrome://extensions/`
3. Enable "Developer mode"
4. Click "Load unpacked" and select the `extension` folder
5. Configure the extension with your API credentials

### AWS Backend

1. Ensure you have AWS CLI installed and configured
2. Navigate to the project directory
3. Run the deployment script:

```bash
./scripts/deploy.sh
```

## ⚙️ Configuration

### Extension Settings

- **API URL**: The endpoint for your deployed AWS API
- **Password**: Basic auth password for API access
- **Anthropic API Key**: Your Claude API key from [console.anthropic.com](https://console.anthropic.com)

## 📋 Usage

1. Navigate to any web page you want to summarize
2. Click the Page Summarizer extension icon
3. Select your preferred summary type and options
4. Click "Summarize Page"
5. View the generated summary in the sidebar

## 🔄 How It Works

1. The extension captures the current page's HTML content
2. Content is sent to the AWS Lambda function via API Gateway
3. Trafilatura extracts the main content from the HTML
4. Claude AI generates a summary based on the selected mode
5. For large pages, content is processed in chunks and combined
6. The summary is returned to the extension and displayed

## 🧩 Technical Details

### Content Extraction

The backend uses [Trafilatura](https://github.com/adbar/trafilatura) to extract the main content from web pages, filtering out navigation, ads, and other non-essential elements.

### AI Summarization

Summaries are generated using Anthropic's Claude models, with different prompts based on the selected mode:
- Standard mode focuses on extracting key information
- Debate mode critically analyzes the content for logical fallacies and provides counter-arguments

### Chunking Strategy

For large pages, the content is split into manageable chunks, processed separately, and then combined:
- In standard mode, a meta-summary is created from all chunk summaries
- In debate mode, individual analyses are presented side by side for comprehensive coverage

## 🔒 Security

- API access is protected with Basic Authentication
- API keys are stored securely in the extension's local storage
- AWS resources use IAM roles with least privilege principles

## 🛠️ Development

### Updating the Lambda Function

To update the Lambda function after making changes:

```bash
./scripts/update_lambda.sh
```

### Extension Development

The extension follows standard Chrome extension architecture:
- `manifest.json`: Extension configuration
- `popup.html/js`: User interface for the extension
- `options.html/js`: Settings configuration
- `sidebar.html/js`: Summary display

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgements

- [Trafilatura](https://github.com/adbar/trafilatura) for content extraction
- [Anthropic Claude](https://www.anthropic.com/claude) for AI summarization
- AWS for serverless infrastructure
