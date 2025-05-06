function init() {
  chrome.storage.local.get(
    { apiUrl: "", password: "", anthropicApiKey: "" },
    (items) => {
      if(items.apiUrl == "" || items.password == "" || items.anthropicApiKey == ""){
        if (chrome.runtime.openOptionsPage) {
          chrome.runtime.openOptionsPage();
        } else {
          window.open(chrome.runtime.getURL('options.html'));
        }
      }
    }
  );

  // Initialize loading state
  document.isInitialized = false;
  document.getElementById('summarize').disabled = true;
  status("Loading page information...");

  // Get page information
  getPageInfo()
    .then((pageInfo) => {
      // Store the results
      document.pageUrl = pageInfo.url;
      document.pageTitle = pageInfo.title;
      document.pageHtml = pageInfo.html;

      // Mark as initialized and enable button
      document.isInitialized = true;
      document.getElementById('summarize').disabled = false;
      status("Ready to summarize!");
    })
    .catch(error => {
      console.error("Error initializing:", error);
      status("Error loading page information. Please try refreshing the page.", true);
    });
}

function status(text, clear = false) {
  const status = document.getElementById('status');
  status.textContent = text;
  if(clear){
    setTimeout(() => {
      status.textContent = '';
    }, 5000);
  }
}

async function summarize() {
  // Check if initialization is complete
  if (!document.isInitialized) {
    status("Still loading page information. Please wait...", true);
    return;
  }
  
  status("Summarizing page...");
  
  try {
    // Get page info
    const pageUrl = document.pageUrl;
    const pageTitle = document.pageTitle;
    const pageHtml = document.pageHtml;
    
    // Get user options
    const summaryType = document.getElementById('summary-type').value;
    const includeComments = document.getElementById('include-comments').checked;
    
    // Get configuration from storage
    const config = await new Promise((resolve) => {
      chrome.storage.local.get(['apiUrl', 'password', 'user', 'anthropicApiKey', 'claudeModel'], (result) => {
        resolve(result);
      });
    });

    const apiUrl = config.apiUrl;
    const password = config.password;
    const user = config.user || "admin";
    const anthropicApiKey = config.anthropicApiKey;
    const claudeModel = config.claudeModel || "claude-3-haiku-20240307";

    // Prepare request data
    const data = {
      page_url: pageUrl,
      api_key: anthropicApiKey,
      model: claudeModel,
      html_content: pageHtml,
      include_comments: includeComments,
      mode: summaryType
    };

    // Start polling for results
    await pollForResults(apiUrl, user, password, data, pageUrl, pageTitle);
  } catch (error) {
    console.error('Error summarizing page:', error);
    status('Error: ' + (error.message || 'Failed to summarize page'), true);
  }
}

async function pollForResults(apiUrl, user, password, data, pageUrl, pageTitle, attempt = 0) {
  try {
    status(`Processing page${attempt > 0 ? ` (attempt ${attempt + 1})` : ''}...`);
    
    // Make API request
    const response = await makePutRequestWithBasicAuth(apiUrl, user, password, data);
    
    console.log('Lambda response:', response);
    
    if (response) {
      // Check if processing is complete
      if (response.summary) {
        // Store the summary in Chrome storage
        chrome.storage.local.set({
          pageSummary: response.summary,
          pageTitle: pageTitle,
          pageUrl: pageUrl
        });
        
        // Open the sidebar
        openSidebar();
        
        status('Summary generated!', true);
      } 
      // If processing is still ongoing - check for any status that indicates processing
      else if (
        response.status === 'processing' ||
        response.status === 'summarizing' ||
        (response.status && String(response.status).includes('summariz')) ||
        (response.message && response.message.includes('Processing')) ||
        (response.message && response.message.includes('processing'))
      ) {
        status(`Processing page: ${response.status || 'in progress'}...`);
        
        // Poll again after 5 seconds
        setTimeout(() => {
          pollForResults(apiUrl, user, password, data, pageUrl, pageTitle, attempt + 1);
        }, 5000);
      } 
      else if (response.success === false) {
        status('Error: ' + (response.message || 'Failed to generate summary'), true);
      }
      else {
        // If we can't determine the status but the response exists, assume it's still processing
        status(`Processing page (status unknown)...`);
        
        // Poll again after 5 seconds
        setTimeout(() => {
          pollForResults(apiUrl, user, password, data, pageUrl, pageTitle, attempt + 1);
        }, 5000);
      }
    } else {
      status('Error: Failed to generate summary - no response', true);
    }
  } catch (error) {
    console.error('Error during polling:', error);
    
    // Retry on 504 Gateway Timeout errors
    if (error.message && error.message.includes('504')) {
      status('Server timeout, retrying in 5 seconds...');
      
      // Poll again after 5 seconds
      setTimeout(() => {
        pollForResults(apiUrl, user, password, data, pageUrl, pageTitle, attempt + 1);
      }, 5000);
    } else {
      status('Error: ' + (error.message || 'Failed to summarize page'), true);
    }
  }
}

function openSidebar() {
  // Open the sidebar in a new tab
  chrome.tabs.create({
    url: chrome.runtime.getURL('sidebar.html')
  });
}

async function getPageInfo() {
  // Execute script in the active tab to get page information
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  
  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    function: () => {
      // This function runs in the context of the web page
      return {
        url: document.location.href,
        title: document.title,
        html: document.documentElement.outerHTML
      };
    }
  });

  // Results is an array of execution results
  return results[0].result;
}

async function makePutRequestWithBasicAuth(url, username, password, data) {
  try {
    // Create the Authorization header by encoding username:password in base64
    const credentials = btoa(`${username}:${password}`);
    
    const response = await fetch(url, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Basic ${credentials}`
      },
      body: JSON.stringify(data)
    });

    const responseClone = response.clone()
    
    if (!response.ok) {
      const errorText = await responseClone.text();
      console.error(`Error Text: ${errorText}`);
      throw new Error(`HTTP error! Status: ${response.status}`);
    }
    
    return await response.json(); // Parse JSON response
  } catch (error) {
    console.error('Error making PUT request:', error);
    throw error;
  }
}

document.addEventListener('DOMContentLoaded', init);
document.getElementById('summarize').addEventListener('click', summarize);
