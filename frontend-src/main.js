// Configuration.
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const NETWORK = import.meta.env.VITE_NETWORK || 'base-sepolia';

// Helper: Get block explorer URL for transaction.
function getExplorerUrl(network, txHash) {
  const explorers = {
    'base-sepolia': `https://sepolia.basescan.org/tx/${txHash}`,
    base: `https://basescan.org/tx/${txHash}`,
  };
  return explorers[network] || null;
}

// State.
let walletClient = null;
let fetchWithPay = null;
let currentAccount = null;
let isServiceHealthy = true;

// DOM elements.
const connectButton = document.getElementById('connectButton');
const walletStatus = document.getElementById('walletStatus');
const walletAddress = document.getElementById('walletAddress');
const networkBadge = document.getElementById('networkBadge');
const querySection = document.getElementById('querySection');
const queryForm = document.getElementById('queryForm');
const submitButton = document.getElementById('submitButton');
const queryInput = document.getElementById('queryInput');
const charCount = document.getElementById('charCount');
const loadingSection = document.getElementById('loadingSection');
const loadingMessage = document.getElementById('loadingMessage');
const resultSection = document.getElementById('resultSection');
const resultContent = document.getElementById('resultContent');
const errorContainer = document.getElementById('errorContainer');
const healthBanner = document.getElementById('healthBanner');
const healthTitle = document.getElementById('healthTitle');
const healthMessage = document.getElementById('healthMessage');
const apiDocsLink = document.getElementById('apiDocsLink');
const apiUrlLink = document.getElementById('apiUrlLink');

// Set API docs link to point to backend.
apiDocsLink.href = `${API_URL}/docs`;

// Set API URL link in footer.
apiUrlLink.href = `${API_URL}/docs`;
apiUrlLink.textContent = API_URL;

// Connect wallet.
connectButton.addEventListener('click', async () => {
  try {
    if (!window.ethereum) {
      showError('No Ethereum wallet detected. Please install MetaMask or Coinbase Wallet.');
      return;
    }

    // Dynamically import wallet libraries only when needed.
    const [{ createWalletClient, custom }, { baseSepolia, base }, { wrapFetchWithPayment }] =
      await Promise.all([import('viem'), import('viem/chains'), import('x402-fetch')]);

    // Request account access.
    const accounts = await window.ethereum.request({
      method: 'eth_requestAccounts',
    });

    if (!accounts || accounts.length === 0) {
      throw new Error('No accounts found');
    }

    currentAccount = accounts[0];

    // Select chain based on network configuration.
    const chain = NETWORK === 'base' ? base : baseSepolia;

    // Check if we need to switch networks.
    const currentChainId = await window.ethereum.request({ method: 'eth_chainId' });
    const targetChainId = `0x${chain.id.toString(16)}`;

    if (currentChainId !== targetChainId) {
      try {
        // Try to switch to the target network.
        await window.ethereum.request({
          method: 'wallet_switchEthereumChain',
          params: [{ chainId: targetChainId }],
        });
      } catch (switchError) {
        // This error code indicates that the chain has not been added to MetaMask.
        if (switchError.code === 4902) {
          try {
            await window.ethereum.request({
              method: 'wallet_addEthereumChain',
              params: [
                {
                  chainId: targetChainId,
                  chainName: chain.name,
                  nativeCurrency: chain.nativeCurrency,
                  rpcUrls: chain.rpcUrls.default.http,
                  blockExplorerUrls: chain.blockExplorers?.default
                    ? [chain.blockExplorers.default.url]
                    : [],
                },
              ],
            });
          } catch (addError) {
            throw new Error(`Failed to add ${chain.name} network: ${addError.message}`);
          }
        } else {
          throw new Error(`Failed to switch to ${chain.name}: ${switchError.message}`);
        }
      }
    }

    // Create wallet client from browser wallet.
    walletClient = createWalletClient({
      account: currentAccount,
      chain,
      transport: custom(window.ethereum),
    });

    // Wrap fetch with payment handling.
    // maxValue: 10000000 = $10 worth of USDC (in atomic units).
    fetchWithPay = wrapFetchWithPayment(fetch, walletClient, 10000000);

    // Update UI.
    connectButton.classList.add('connected');
    walletStatus.classList.add('connected');
    walletAddress.textContent = `${currentAccount.slice(0, 6)}...${currentAccount.slice(-4)}`;
    networkBadge.textContent = chain.name;
    querySection.classList.add('active');

    // Only enable submit button if service is healthy
    submitButton.disabled = !isServiceHealthy;
  } catch (error) {
    showError(`Failed to connect wallet: ${error.message}`);
  }
});

// Handle account changes.
if (window.ethereum) {
  window.ethereum.on('accountsChanged', (accounts) => {
    if (accounts.length === 0) {
      // User disconnected wallet.
      resetWallet();
    } else if (accounts[0] !== currentAccount) {
      // User switched account.
      window.location.reload();
    }
  });

  window.ethereum.on('chainChanged', () => {
    // Reload on chain change.
    window.location.reload();
  });
}

// Submit query.
queryForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  // Don't submit if button is disabled (wallet not connected).
  if (submitButton.disabled) {
    showError('Please connect your wallet first');
    return;
  }

  // Check if service is healthy before submitting
  if (!isServiceHealthy) {
    showError('Service is currently overloaded. Please wait a few minutes and try again.');
    return;
  }

  const query = queryInput.value.trim();

  if (!query || query.length < 10 || query.length > 256) {
    showError('Query must be between 10 and 256 characters');
    return;
  }

  // Validate query pattern (matches backend validation).
  const allowedPattern = /^[a-zA-Z0-9\s.,?!\-'"":;()/@#$%&+=]+$/;
  if (!allowedPattern.test(query)) {
    showError(
      'Query contains invalid characters. Only alphanumeric and common punctuation allowed.'
    );
    return;
  }

  if (!fetchWithPay) {
    showError('Please connect your wallet first');
    return;
  }

  try {
    hideError();
    showLoading('Submitting query with payment...');
    submitButton.disabled = true;

    // Submit query - payment will be handled automatically by x402-fetch.
    const response = await fetchWithPay(`${API_URL}/api/v1/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const result = await response.json();

    // Poll for results
    await pollForResults(result.job_id);
  } catch (error) {
    // Parse error message for better UX.
    let errorMessage = error.message;

    // Handle 402 payment errors - extract just the relevant error.
    if (errorMessage.includes('HTTP 402:')) {
      try {
        const jsonMatch = errorMessage.match(/\{.*\}/);
        if (jsonMatch) {
          const errorData = JSON.parse(jsonMatch[0]);
          if (errorData.error) {
            errorMessage = `Payment failed: ${errorData.error}`;
          }
        }
      } catch {
        // If parsing fails, use original message.
      }
    }

    showError(`Failed to submit query: ${errorMessage}`);
    hideLoading();
    // Only re-enable if wallet is connected.
    if (fetchWithPay) {
      submitButton.disabled = false;
    }
  }
});

// Poll for results.
async function pollForResults(jobId) {
  const maxPolls = 90; // 6 minutes max.
  const pollInterval = 4000; // 4 seconds.

  showLoading('Querying multiple AI providers...');

  for (let i = 0; i < maxPolls; i++) {
    await new Promise((resolve) => setTimeout(resolve, pollInterval));

    try {
      const response = await fetchWithPay(`${API_URL}/api/v1/query/${jobId}`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${await response.text()}`);
      }

      const data = await response.json();

      if (data.status === 'completed') {
        displayResult(data);
        hideLoading();
        // Only re-enable if wallet is connected.
        if (fetchWithPay) {
          submitButton.disabled = false;
        }
        return;
      } else if (data.status === 'failed') {
        throw new Error(data.error || 'Job failed');
      }

      // Update loading message based on status.
      const statusMessages = {
        pending: 'Queuing your request...',
        processing: 'Analyzing responses from AI providers...',
      };
      loadingMessage.textContent = statusMessages[data.status] || 'Processing your query...';
    } catch (error) {
      showError(`Failed to get results: ${error.message}`);
      hideLoading();
      // Only re-enable if wallet is connected.
      if (fetchWithPay) {
        submitButton.disabled = false;
      }
      return;
    }
  }

  showError('Timeout waiting for results (6 minutes)');
  hideLoading();
  // Only re-enable if wallet is connected.
  if (fetchWithPay) {
    submitButton.disabled = false;
  }
}

// Display result.
function displayResult(jobData) {
  const result = jobData.result;
  const decision = result.final_decision.toLowerCase();
  const confidence = (result.final_confidence * 100).toFixed(1);

  // Parse and format explanation using the shared function.
  const explanationHtml = formatExplanation(result.explanation);

  // Format payment info if available.
  let paymentInfoHtml = '';
  if (jobData.payer_address || jobData.tx_hash) {
    const shortAddress = jobData.payer_address
      ? `${jobData.payer_address.slice(0, 6)}...${jobData.payer_address.slice(-4)}`
      : 'Unknown';

    const explorerUrl =
      jobData.tx_hash && jobData.network ? getExplorerUrl(jobData.network, jobData.tx_hash) : null;

    paymentInfoHtml = `
      <div class="payment-info">
        <div class="payment-item">
          <span class="payment-label">Paid by:</span>
          <span class="payment-value">${escapeHtml(shortAddress)}</span>
        </div>
        ${
          explorerUrl
            ? `
          <div class="payment-item">
            <a href="${explorerUrl}" target="_blank" rel="noopener noreferrer" class="payment-link">
              View Transaction ↗
            </a>
          </div>
        `
            : ''
        }
      </div>
    `;
  }

  // Format cryptographic verification info if available.
  let verificationHtml = '';
  if (result.signature && result.public_key) {
    verificationHtml = `
      <details class="llm-details">
        <summary>🔐 Cryptographic Verification</summary>
        <div class="llm-responses">
          <div class="llm-response">
            <h5>ROFL TEE Signature</h5>
            <p style="word-break: break-all; font-family: monospace; font-size: 0.85em; color: #a1a1aa;">${escapeHtml(result.signature)}</p>
            <p style="margin-top: 12px;"><strong>Public Key:</strong></p>
            <p style="word-break: break-all; font-family: monospace; font-size: 0.85em; color: #a1a1aa;">${escapeHtml(result.public_key)}</p>
            <p style="margin-top: 12px; font-size: 0.9em; color: #71717a;">
              This response is cryptographically signed by code running inside the ROFL TEE.
              The public key can be verified against the on-chain attested state in the
              <a href="https://github.com/ptrus/rofl-registry" target="_blank" rel="noopener noreferrer" style="color: #10b981; text-decoration: none; border-bottom: 1px solid transparent;" onmouseover="this.style.borderBottomColor='#10b981'" onmouseout="this.style.borderBottomColor='transparent'">Oasis ROFL registry</a>.
            </p>
          </div>
        </div>
      </details>
    `;
  }

  let html = `
    <div class="result-card">
      <div class="result-header">
        <h3>Query: ${escapeHtml(result.query)}</h3>
        ${paymentInfoHtml}
      </div>

      <div class="final-decision ${decision}">
        <h4>Final Decision: ${decision.toUpperCase()}</h4>
        <div class="confidence-bar">
          <div class="confidence-fill" style="width: ${confidence}%"></div>
        </div>
        <p class="confidence-text">Confidence: ${confidence}%</p>
      </div>

      <div class="explanation">
        <h4>Consensus Analysis</h4>
        ${explanationHtml}
      </div>

      <details class="llm-details">
        <summary>View Individual LLM Responses</summary>
        <div class="llm-responses">
  `;

  for (const llm of result.llm_responses) {
    const llmConfidence = (llm.confidence * 100).toFixed(1);

    html += `
      <div class="llm-response ${llm.error ? 'error' : ''}">
        <h5>${escapeHtml(llm.provider.toUpperCase())}</h5>
        <p class="model-name"><em>${escapeHtml(llm.model || 'unknown')}</em></p>
        ${
          llm.error
            ? `<p class="error-text">Request failed</p>`
            : `
            <p><strong>Decision:</strong> ${llm.decision.toUpperCase()}</p>
            <p><strong>Confidence:</strong> ${llmConfidence}%</p>
            <p><strong>Reasoning:</strong> ${escapeHtml(llm.reasoning)}</p>
          `
        }
      </div>
    `;
  }

  html += `
        </div>
      </details>

      ${verificationHtml}
    </div>
  `;

  resultContent.innerHTML = html;
  resultSection.classList.add('active');
}

// Helper functions.
function showLoading(message) {
  loadingMessage.textContent = message;
  loadingSection.style.display = 'block';
  resultSection.classList.remove('active');
}

function hideLoading() {
  loadingSection.style.display = 'none';
}

function showError(message) {
  errorContainer.innerHTML = `
    <div class="error-banner">
      <div class="error-icon">⚠</div>
      <div class="error-content">
        <strong>Error</strong>
        <p>${escapeHtml(message)}</p>
      </div>
      <button onclick="this.parentElement.remove()" class="error-close">×</button>
    </div>
  `;
}

function hideError() {
  errorContainer.innerHTML = '';
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatMarkdown(text) {
  // 1. Escape HTML first to prevent XSS.
  const escaped = escapeHtml(text);

  // 2. Then apply markdown formatting on escaped text.
  return escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

function formatTimeAgo(timestamp) {
  const now = new Date();

  // Handle ISO timestamp - backend sends naive timestamps (no timezone).
  // Append 'Z' to treat as UTC if it doesn't already have timezone info.
  let timestampStr = timestamp;
  if (
    timestamp.includes('T') &&
    !timestamp.includes('Z') &&
    !timestamp.includes('+') &&
    !timestamp.includes('-', 10)
  ) {
    timestampStr = timestamp + 'Z';
  }

  const past = new Date(timestampStr);

  // Check if date is valid.
  if (isNaN(past.getTime())) {
    return '';
  }

  const diffMs = now - past;
  const seconds = Math.floor(diffMs / 1000);

  if (seconds < 0) {
    // Future timestamp, probably clock skew.
    return 'just now';
  }

  if (seconds < 60) return 'just now';

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(seconds / 3600);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(seconds / 86400);
  if (days < 7) return `${days}d ago`;

  // For older dates, show the actual date.
  return past.toLocaleDateString();
}

function formatExplanation(explanation) {
  if (!explanation) return '';

  let html = '';
  const lines = explanation.split('\n');
  let currentSection = '';
  let inProviderAssessments = false;

  lines.forEach((line) => {
    const trimmed = line.trim();

    // Skip the redundant "Final Decision" line.
    if (trimmed.startsWith('**Final Decision:')) {
      return;
    }

    // Main headers (Voting Summary, Total Weight Used, etc.).
    if (trimmed.startsWith('**') && trimmed.endsWith('**')) {
      if (currentSection) {
        if (inProviderAssessments) {
          html += `</div>`; // Close provider-grid.
          inProviderAssessments = false;
        }
        html += `</div>`; // Close section.
      }
      const headerText = trimmed.replace(/\*\*/g, '');
      html += `<div class="explanation-section">`;
      html += `<h5 class="explanation-header">${escapeHtml(headerText)}</h5>`;

      // Check if this is the Individual Provider Assessments section.
      if (headerText.includes('Individual Provider Assessments')) {
        html += `<div class="provider-grid">`;
        inProviderAssessments = true;
      }

      currentSection = headerText;
    }
    // Bullet points.
    else if (trimmed.startsWith('-')) {
      const text = trimmed.substring(1).trim();

      // If in provider assessments, format as grid items.
      if (inProviderAssessments) {
        // Parse provider line: **PROVIDER** (weight: X): DECISION (confidence: Y).
        const match = text.match(
          /\*\*([^*]+)\*\*\s*\(weight:\s*([\d.]+)\):\s*(\w+)\s*\(confidence:\s*([\d.]+)\)/
        );
        if (match) {
          const [, provider, weight, decision, confidence] = match;
          const decisionClass = decision.toLowerCase();
          html += `
            <div class="provider-item ${decisionClass}">
              <div class="provider-name">${escapeHtml(provider)}</div>
              <div class="provider-decision">${decision}</div>
              <div class="provider-stats">
                <span>Weight: ${weight}</span>
                <span>Confidence: ${(parseFloat(confidence) * 100).toFixed(0)}%</span>
              </div>
            </div>
          `;
        } else {
          // Fallback to regular formatting.
          html += `<div class="explanation-item">${formatMarkdown(text)}</div>`;
        }
      } else {
        // Regular bullet point.
        html += `<div class="explanation-item">${formatMarkdown(text)}</div>`;
      }
    }
    // Regular text with bold support.
    else if (trimmed) {
      html += `<p class="explanation-text">${formatMarkdown(trimmed)}</p>`;
    }
  });

  if (currentSection) {
    if (inProviderAssessments) {
      html += `</div>`; // Close provider-grid.
    }
    html += `</div>`; // Close section.
  }

  return html;
}

function resetWallet() {
  walletClient = null;
  fetchWithPay = null;
  currentAccount = null;
  connectButton.classList.remove('connected');
  walletStatus.classList.remove('connected');
  querySection.classList.remove('active');
  resultSection.classList.remove('active');
  submitButton.disabled = true;
}

// Character counter.
if (queryInput && charCount) {
  charCount.textContent = queryInput.value.length;
  queryInput.addEventListener('input', function () {
    if (charCount) {
      charCount.textContent = this.value.length;
    }
  });
}

// Recent resolutions feed.
let recentJobIds = new Set();

function fetchRecentResolutions() {
  fetch(`${API_URL}/api/v1/recent?limit=5`)
    .then((response) => response.json())
    .then((jobs) => {
      const container = document.getElementById('recent-resolutions');

      if (jobs.length === 0 && recentJobIds.size === 0) {
        container.innerHTML =
          '<p class="no-resolutions">No recent resolutions yet. Be the first!</p>';
        return;
      }

      // Filter out jobs we already have.
      const newJobs = jobs.filter((job) => !recentJobIds.has(job.job_id));

      // Remove "no resolutions" message if it exists and we have new jobs.
      if (newJobs.length > 0) {
        const noResMessage = container.querySelector('.no-resolutions');
        if (noResMessage) {
          noResMessage.remove();
        }
      }

      // Add new jobs with slide-in animation.
      newJobs.forEach((job) => {
        recentJobIds.add(job.job_id);
        const html = createCollapsedResult(job);
        container.insertAdjacentHTML('afterbegin', html);

        // Trigger slide-in animation.
        setTimeout(() => {
          const element = document.querySelector(`[data-job-id="${job.job_id}"]`);
          if (element) {
            element.classList.add('slide-in');
          }
        }, 10);
      });

      // Keep only 5 most recent.
      const items = container.querySelectorAll('.recent-result');
      if (items.length > 5) {
        for (let i = 5; i < items.length; i++) {
          const jobId = items[i].getAttribute('data-job-id');
          recentJobIds.delete(jobId);
          items[i].remove();
        }
      }
    })
    .catch(() => {
      // Silently handle error fetching recent resolutions
    });
}

function createCollapsedResult(job) {
  if (!job.result) return '';

  const result = job.result;
  const decisionClass = result.final_decision.toLowerCase();
  const decisionIcon = decisionClass === 'yes' ? '✓' : decisionClass === 'no' ? '✗' : '?';

  // Format timestamp.
  const timestamp = job.completed_at ? formatTimeAgo(job.completed_at) : '';

  return `
    <details class="recent-result" data-job-id="${job.job_id}">
      <summary class="recent-summary ${decisionClass}">
        <span class="decision-icon">${decisionIcon}</span>
        <span class="query-text">${escapeHtml(result.query)}</span>
        <div class="recent-meta">
          ${timestamp ? `<span class="recent-time">${timestamp}</span>` : ''}
          <span class="confidence-badge">${(result.final_confidence * 100).toFixed(0)}%</span>
        </div>
      </summary>
      <div class="recent-details">
        ${
          job.payer_address || job.tx_hash
            ? `
          <div class="payment-info">
            ${
              job.payer_address
                ? `
              <div class="payment-item">
                <span class="payment-label">Paid by:</span>
                <span class="payment-value">${job.payer_address.slice(0, 6)}...${job.payer_address.slice(-4)}</span>
              </div>
            `
                : ''
            }
            ${
              job.tx_hash && job.network
                ? `
              <div class="payment-item">
                <a href="${getExplorerUrl(job.network, job.tx_hash)}" target="_blank" rel="noopener noreferrer" class="payment-link">
                  View Transaction ↗
                </a>
              </div>
            `
                : ''
            }
          </div>
        `
            : ''
        }
        <div class="explanation">
          <h4>Consensus Analysis</h4>
          ${formatExplanation(result.explanation)}
        </div>
        <details class="llm-details">
          <summary>View Individual LLM Responses</summary>
          <div class="llm-responses">
            ${result.llm_responses
              .map((response) => {
                const errorClass = response.error ? 'error' : '';
                const providerLabel = escapeHtml((response.provider || '').toUpperCase());
                return `
                <div class="llm-response ${errorClass}">
                  <h5>${providerLabel}</h5>
                  ${
                    response.error
                      ? `<p class="error-text">Request failed</p>`
                      : `
                      <p><strong>Decision:</strong> ${response.decision.toUpperCase()}</p>
                      <p><strong>Confidence:</strong> ${(response.confidence * 100).toFixed(1)}%</p>
                      <p><strong>Reasoning:</strong> ${escapeHtml(response.reasoning)}</p>
                    `
                  }
                </div>
              `;
              })
              .join('')}
          </div>
        </details>
        ${
          result.signature && result.public_key
            ? `
        <details class="llm-details">
          <summary>🔐 Cryptographic Verification</summary>
          <div class="llm-responses">
            <div class="llm-response">
              <h5>ROFL TEE Signature</h5>
              <p style="word-break: break-all; font-family: monospace; font-size: 0.85em; color: #a1a1aa;">${escapeHtml(result.signature)}</p>
              <p style="margin-top: 12px;"><strong>Public Key:</strong></p>
              <p style="word-break: break-all; font-family: monospace; font-size: 0.85em; color: #a1a1aa;">${escapeHtml(result.public_key)}</p>
              <p style="margin-top: 12px; font-size: 0.9em; color: #71717a;">
                This response is cryptographically signed by code running inside the ROFL TEE.
                The public key can be verified against the on-chain attested state in the
                <a href="https://github.com/ptrus/rofl-registry" target="_blank" rel="noopener noreferrer" style="color: #10b981; text-decoration: none; border-bottom: 1px solid transparent;" onmouseover="this.style.borderBottomColor='#10b981'" onmouseout="this.style.borderBottomColor='transparent'">Oasis ROFL registry</a>.
              </p>
            </div>
          </div>
        </details>
        `
            : ''
        }
      </div>
    </details>
  `;
}

// Initial fetch and poll every 10 seconds.
fetchRecentResolutions();
setInterval(fetchRecentResolutions, 10000);

// Health check monitoring.
async function checkServiceHealth() {
  try {
    const response = await fetch(`${API_URL}/health`);
    const healthData = await response.json();

    const status = healthData.status || 'healthy';

    // Update UI based on health status.
    if (status === 'unhealthy') {
      isServiceHealthy = false;
      healthBanner.className = 'health-banner unhealthy';
      healthTitle.textContent = 'Service Overloaded';

      const queuedJobs = healthData.queued_jobs || 0;
      healthMessage.textContent = `The service is currently experiencing high load (${queuedJobs} jobs queued). Submissions are temporarily disabled. Please try again in a few minutes.`;

      // Disable submit button.
      if (submitButton && fetchWithPay) {
        submitButton.disabled = true;
      }
    } else if (status === 'degraded') {
      isServiceHealthy = true;
      healthBanner.className = 'health-banner degraded';
      healthTitle.textContent = 'Service Performance Degraded';
      healthMessage.textContent =
        'The service is experiencing some issues, but queries can still be submitted. Results may take longer than usual.';

      // Re-enable submit button if wallet is connected.
      if (submitButton && fetchWithPay) {
        submitButton.disabled = false;
      }
    } else {
      // Healthy - hide banner.
      isServiceHealthy = true;
      healthBanner.className = 'health-banner';

      // Re-enable submit button if wallet is connected.
      if (submitButton && fetchWithPay) {
        submitButton.disabled = false;
      }
    }
  } catch {
    // On error, assume healthy to not block users unnecessarily.
    isServiceHealthy = true;
    healthBanner.className = 'health-banner';
  }
}

// Check health immediately on page load.
checkServiceHealth();

// Poll health every 30 seconds.
setInterval(checkServiceHealth, 30000);
