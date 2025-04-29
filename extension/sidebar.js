// Function to load and display the summary from Chrome storage
function loadSummary() {
  const summaryDiv = document.getElementById('summary');
  
  // Display loading message
  summaryDiv.innerHTML = '<p>Loading summary...</p>';
  
  // Get the summary from Chrome storage
  chrome.storage.local.get(['pageSummary', 'pageTitle', 'pageUrl'], function(result) {
    if (result.pageSummary) {
      // Add title if available
      let content = '';
      if (result.pageTitle) {
        content += `<h1>${result.pageTitle}</h1>`;
      }
      
      // Add the summary content (already HTML formatted)
      content += result.pageSummary;
      
      // Update the summary div
      summaryDiv.innerHTML = content;
    } else {
      // No summary found
      summaryDiv.innerHTML = '<p>No summary available. Please generate a summary from the extension popup.</p>';
    }
  });
}

// Listen for messages from the popup
chrome.runtime.onMessage.addListener(function(request, sender, sendResponse) {
  if (request.action === "updateSummary") {
    const summaryDiv = document.getElementById('summary');
    
    // Add title if available
    let content = '';
    if (request.pageTitle) {
      content += `<h1>${request.pageTitle}</h1>`;
    }
    
    // Add the summary content
    content += request.summary;
    
    // Update the summary div
    summaryDiv.innerHTML = content;
    
    // Send response to confirm update
    sendResponse({status: "Summary updated"});
  }
});

// Initialize when the page loads
document.addEventListener('DOMContentLoaded', loadSummary);
