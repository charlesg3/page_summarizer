const defaultApiUrl = "https://zu4ca9gehl.execute-api.us-east-2.amazonaws.com/prod/api";
const defaultClaudeModel = "claude-3-7-sonnet-latest";

// Saves options to chrome.storage
const saveOptions = () => {
  const apiUrl = document.getElementById('api-url').value;
  const password = document.getElementById('password').value;
  const anthropicApiKey = document.getElementById('anthropic-api-key').value;

  chrome.storage.local.set(
    { 
      apiUrl: apiUrl, 
      password: password, 
      user: "admin",
      anthropicApiKey: anthropicApiKey,
      claudeModel: defaultClaudeModel
    },
    () => {
      // Update status to let user know options were saved.
      const status = document.getElementById('status');
      status.textContent = 'Options saved.';
      setTimeout(() => {
        status.textContent = '';
      }, 2000);
    }
  );
};

// Restores select box and checkbox state using the preferences
// stored in chrome.storage.
const restoreOptions = () => {
  console.log("Restoring options");
  chrome.storage.local.get(
    { 
      apiUrl: defaultApiUrl, 
      password: "",
      anthropicApiKey: ""
    },
    (items) => {
      document.getElementById('api-url').value = items.apiUrl;
      document.getElementById('password').value = items.password;
      document.getElementById('anthropic-api-key').value = items.anthropicApiKey;
    }
  );
};

document.addEventListener('DOMContentLoaded', restoreOptions);
document.getElementById('save').addEventListener('click', saveOptions);
