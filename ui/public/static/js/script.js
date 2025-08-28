// Configuration
const API_BASE = '';
let currentTab = 'available';
let useCache = true;
let wifiDirect = false;
let serverOnline = true; // Track server status
let pendingRequests = new Set(); // Track pending requests

// Server connectivity check
async function checkServerConnectivity() {
    try {
        const response = await fetch('health', { 
            method: 'GET',
            signal: AbortSignal.timeout(3000) // 3 second timeout
        });
        if (response.ok) {
            if (!serverOnline) {
                console.log('Server is back online');
                serverOnline = true;
                updateServerStatusIndicator(true);
            }
            return true;
        }
    } catch (error) {
        if (serverOnline) {
            console.log('Server is busy/restarting');
            serverOnline = false;
            updateServerStatusIndicator(false);
        }
        return false;
    }
    return false;
}

// Enhanced fetch with server status handling
async function safeFetch(url, options = {}) {
    const requestId = Math.random().toString(36);
    pendingRequests.add(requestId);
    
    try {
        // Check server connectivity first
        const isOnline = await checkServerConnectivity();
        if (!isOnline) {
            throw new Error('Server is busy or restarting');
        }
        
        const response = await fetch(url, {
            ...options,
            signal: AbortSignal.timeout(10000) // 10 second timeout
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return response;
    } catch (error) {
        console.error(`Request failed (${requestId}):`, error);
        throw error;
    } finally {
        pendingRequests.delete(requestId);
    }
}

// Enhanced showToast that respects server status
function showToast(message, type = 'success', force = false) {
    // Don't show toast if server is offline and this isn't a forced message
    if (!serverOnline && !force) {
        console.log('Suppressing toast due to server offline:', message);
        return;
    }
    
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.classList.add('show');
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Centralized error handling function
function handleError(error, context, fallbackMessage) {
    console.error(`Error in ${context}:`, error);
    if (!serverOnline) {
        showToast('Server is busy, please wait...', 'error', true);
    } else {
        showToast(fallbackMessage, 'error', true);
    }
}

// Centralized error response handling
function handleErrorResponse(response, container, context) {
    if (response && typeof response === 'object' && response.error) {
        const errorType = response.error;
        const errorMessage = response.message || 'An error occurred';
        
        switch (errorType) {
            case 'battery_low':
                showErrorState(container, 'battery-quarter', 'Battery is low. Please charge the device.', true, 'Battery is low. Please charge the device.');
                break;
            case 'scan_failed':
                showErrorState(container, 'exclamation-triangle', 'Failed to scan networks. Please try again.', true, 'Failed to scan networks');
                break;
            default:
                showErrorState(container, 'exclamation-triangle', errorMessage, true, errorMessage);
        }
        return true; // Indicates error was handled
    }
    return false; // No error to handle
}

// Helper function to show error UI state
function showErrorState(container, icon, message, showToast = true, toastMessage = null) {
    container.innerHTML = `
        <div class="empty-state">
            <i class="fas fa-${icon}"></i>
            <p>${message}</p>
        </div>
    `;
    if (showToast) {
        const toastMsg = toastMessage || (serverOnline ? message : 'Server is busy, please wait...');
        showToast(toastMsg, 'error', true);
    }
}

// Update server status indicator
function updateServerStatusIndicator(isOnline) {
    const statusElement = document.getElementById('server-status');
    const statusText = document.getElementById('server-status-text');
    
    if (isOnline) {
        statusElement.classList.remove('offline');
        statusText.textContent = 'Online';
    } else {
        statusElement.classList.add('offline');
        statusText.textContent = 'Offline';
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    fetchWiFiDirectStatus();
    init();
    
    // Start periodic server status check
    setInterval(checkServerConnectivity, 5000); // Check every 5 seconds
});

function showTab(tabName) {
    // Don't change tabs if WiFi Direct is active
    if (wifiDirect) {
        return;
    }
    
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Find the clicked tab button and make it active
    const clickedTab = document.querySelector(`[onclick="showTab('${tabName}')"]`);
    if (clickedTab) {
        clickedTab.classList.add('active');
    }

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(tabName).classList.add('active');

    currentTab = tabName;
    // Load content based on tab
    switch(tabName) {
        case 'available':
            refreshNetworks();
            break;
        case 'connected':
            refreshConnected();
            break;
        case 'saved':
            refreshSaved();
            break;
    }
}

async function init(){
            try {
                const response = await fetch(`./get-wifi-direct`);
                if (!response.ok) throw new Error('Failed to fetch WIFI_DIRECT status');    
                const data = await response.json();
                wifiDirect = data.value === true;

                if (wifiDirect){
                    document.getElementById("main-section").style.display = "none";
                }
                else{
                    showTab('available');
                }
            } catch (error) {
                console.error('Error fetching WiFi Direct status:', error);
                showToast('Error loading WiFi Direct status', 'error');
                // Default to showing available tab if there's an error
                showTab('available');
            }
        }

async function refreshNetworks() {
    const container = document.getElementById('available-networks');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        let url = './list-networks';
        
        if (useCache) {
            url += '?use_cache=true';
            useCache = false;
        } else {
            url += '?use_cache=false';
            showToast('Hotspot will restart', 'error', true)
        }

        const response = await safeFetch(url);
        const data = await response.json();
        renderAvailableNetworks(data.networks || []);
    } catch (error) {
        if (!serverOnline) {
            showErrorState(container, 'server', 'Server is busy. Please wait...');
        } else {
            showErrorState(container, 'exclamation-triangle', 'Error loading networks. Please try again.', false);
            handleError(error, 'refreshNetworks', 'Error loading networks');
        }
    }
}

async function refreshConnected() {
    const container = document.getElementById('connected-network');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        const response = await safeFetch(`list-connected`);
        const data = await response.json();
        renderConnectedNetwork(data.connected);
    } catch (error) {
        if (!serverOnline) {
            showErrorState(container, 'server', 'Server is busy. Please wait...');
        } else {
            showErrorState(container, 'wifi-slash', 'Error loading connection status', false);
            handleError(error, 'refreshConnected', 'Error loading connection status');
        }
    }
}

async function refreshSaved() {
    const container = document.getElementById('saved-networks');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        const response = await safeFetch(`list-saved`);
        const data = await response.json();
        renderSavedNetworks(data.saved_networks || []);
    } catch (error) {
        if (!serverOnline) {
            showErrorState(container, 'server', 'Server is busy. Please wait...');
        } else {
            showErrorState(container, 'bookmark', 'Error loading saved networks', false);
            handleError(error, 'refreshSaved', 'Error loading saved networks');
        }
    }
}

function renderAvailableNetworks(networks) {
    const container = document.getElementById('available-networks');
    
    // Handle error responses using centralized function
    if (handleErrorResponse(networks, container, 'renderAvailableNetworks')) {
        return;
    }
    
    if (!networks || networks.length === 0) {
        showErrorState(container, 'search', 'No networks found. Try refreshing.', false);
        return;
    }

    container.innerHTML = networks.map(network => `
        <li class="network-item" onclick="showConnectModal('${escapeHtml(network.ssid)}', '${escapeHtml(network.security)}')">
            <div class="network-info">
                <div class="network-name">
                    <i class="fas fa-wifi"></i> 
                    <span>${escapeHtml(network.ssid)}</span>
                    <span class="badge ${getSecurityBadgeClass(network.security)}">
                        <i class="fas fa-${getSecurityIcon(network.security)}"></i>
                        ${getSecurityLabel(network.security)}
                    </span>
                </div>
                <div class="network-details">
                    Security: ${escapeHtml(network.security)}
                </div>
            </div>
        </li>
    `).join('');
}

function renderConnectedNetwork(network) {
    const container = document.getElementById('connected-network');
    
    // Handle error responses using centralized function
    if (handleErrorResponse(network, container, 'renderConnectedNetwork')) {
        return;
    }
    
    if (!network) {
        showErrorState(container, 'wifi-slash', 'No network connected', false);
        return;
    }

    container.innerHTML = `
        <div class="network-item connected">
            <div class="network-info">
                <div class="network-name">
                    <i class="fas fa-wifi"></i> 
                    <span>${escapeHtml(network.ssid)}</span>
                    <span class="badge badge-success">Connected</span>
                </div>
                <div class="network-details">
                    Interface: ${escapeHtml(network.interface)}<br>
                    Security: ${escapeHtml(network.security)}<br>
                    Signal: ${network.signal_strength}%
                    ${network.ip_address ? `<br>IP: ${escapeHtml(network.ip_address)}` : ''}
                </div>
            </div>
        </div>
    `;
}

function renderSavedNetworks(networks) {
    const container = document.getElementById('saved-networks');
    
    // Handle error responses using centralized function
    if (handleErrorResponse(networks, container, 'renderSavedNetworks')) {
        return;
    }
    
    if (!networks || networks.length === 0) {
        showErrorState(container, 'bookmark', 'No saved networks found', false);
        return;
    }

    container.innerHTML = networks.map(network => `
        <li class="network-item">
            <div class="network-info">
                <div class="network-name">
                    <i class="fas fa-bookmark"></i> ${escapeHtml(network.ssid)}
                </div>
                <div class="network-details">
                    Security: ${escapeHtml(network.security)}
                </div>
            </div>
            <div class="network-actions">
                <button class="btn btn-success" onclick="event.stopPropagation(); connectToSaved('${escapeHtml(network.ssid)}')">
                    <i class="fas fa-link"></i> Connect
                </button>
                <button class="btn btn-danger" onclick="event.stopPropagation(); forgetNetwork('${escapeHtml(network.ssid)}')">
                    <i class="fas fa-trash"></i> Forget
                </button>
            </div>
        </li>
    `).join('');
}

function showConnectModal(ssid, security) {
    document.getElementById('connect-ssid').value = ssid;
    document.getElementById('connect-password').value = '';
    
    const passwordGroup = document.getElementById('password-group');
    if (security === 'none' || security === 'open' || security === '') {
        passwordGroup.style.display = 'none';
    } else {
        passwordGroup.style.display = 'block';
    }
    
    const modal = document.getElementById('connect-modal');
    modal.style.display = 'flex';
    modal.style.justifyContent = 'center';
    modal.style.alignItems = 'center';
    
    // Initialize keyboard for this modal instance
    if (window.initKeyboardForModal) {
        // Small delay to ensure DOM is fully rendered
        setTimeout(function() {
            window.initKeyboardForModal();
        }, 100);
    }
}

function closeModal() {
    document.getElementById('connect-modal').style.display = 'none';
    
    // Keep the keyboard initialized - do not reset the flag
    // This prevents duplicate event listeners from being added
}

document.getElementById('connect-form').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const ssid = document.getElementById('connect-ssid').value;
    const password = document.getElementById('connect-password').value;
    
    closeModal();
    
    try {
        const response = await safeFetch(`connect`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                ssid: ssid,
                passphrase: password || undefined
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(`Connected to ${ssid}`, 'success');
            setTimeout(() => refreshConnected(), 2000);
        } else {
            showToast(`Failed to connect to ${ssid}`, 'error');
        }
    } catch (error) {
        handleError(error, 'connect', `Error connecting to ${ssid}`);
    }
});

async function connectToSaved(ssid) {
    try {
        const response = await safeFetch(`connect`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                ssid: ssid
                // No passphrase needed for saved networks
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(`Connected to ${ssid}`, 'success');
            setTimeout(() => refreshConnected(), 2000);
        } else {
            showToast(`Failed to connect to ${ssid}`, 'error');
        }
    } catch (error) {
        handleError(error, 'connectToSaved', `Error connecting to ${ssid}`);
    }
}

async function forgetNetwork(ssid) {
    if (!confirm(`Are you sure you want to forget "${ssid}"?`)) {
        return;
    }
    
    try {
        const response = await safeFetch(`forget-network`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                ssid: ssid
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(`Forgot network "${ssid}"`, 'success');
            refreshSaved();
        } else {
            showToast(`Failed to forget "${ssid}"`, 'error');
        }
    } catch (error) {
        handleError(error, 'forgetNetwork', `Error forgetting "${ssid}"`);
    }
}

async function forgetAllNetworks() {
    if (!confirm('Are you sure you want to forget ALL saved networks? This cannot be undone.')) {
        return;
    }
    
    try {
        const response = await safeFetch(`forget-all`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({})
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('All networks forgotten', 'success');
            refreshSaved();
        } else {
            showToast('Failed to forget all networks', 'error');
        }
    } catch (error) {
        handleError(error, 'forgetAllNetworks', 'Error forgetting all networks');
    }
}

async function toggleWiFiDirect() {
    try {
        const newValue = !wifiDirect;
        
        // Show immediate feedback that the action is being processed
        showToast(`Toggling WiFi Direct...`, 'success', true);
        
        const response = await safeFetch(`set-wifi-direct`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                value: newValue.toString()
            })
        });
        
        const data = await response.json();
        wifiDirect = data.value === 'true';
        updateWiFiDirectUI(wifiDirect);
        
        // Add haptic feedback for mobile devices
        if (navigator.vibrate) {
            navigator.vibrate(50);
        }
        
        showToast(`WiFi Direct ${wifiDirect ? 'enabled' : 'disabled'}`, 'success');
        
        // Show restart notification
        showToast('Server restarting to apply changes...', 'success', true);
        
        // The server will restart, so we need to wait and reinitialize
        setTimeout(() => {
            console.log('Server restarting, waiting for reconnection...');
            // Wait for server to come back online
            const checkServer = async () => {
                const isOnline = await checkServerConnectivity();
                if (isOnline) {
                    console.log('Server is back online, reinitializing...');
                    showToast('Server restarted successfully', 'success', true);
                    init();
                } else {
                    // Check again in 2 seconds
                    setTimeout(checkServer, 2000);
                }
            };
            checkServer();
        }, 2000);
        
    } catch (error) {
        handleError(error, 'toggleWiFiDirect', 'Error toggling WiFi Direct');
    }
}

function updateWiFiDirectUI(isWifiDirect) {
            const toggleButton = document.getElementById('wifi-direct-toggle');
            const wifiDirectStatus = document.getElementById('wifi-direct-status');
            const mainSection = document.getElementById('main-section');
            
            if (isWifiDirect) {
                // WiFi Direct is ON - hide the main section
                toggleButton.classList.add('active');
                wifiDirectStatus.textContent = 'ON';
                
                // Hide the entire main section
                if (mainSection) mainSection.style.display = 'none';
                
                // Show WiFi Direct message
                showWiFiDirectMessage();
                
            } else {
                // WiFi Direct is OFF - show the main section
                toggleButton.classList.remove('active');
                wifiDirectStatus.textContent = 'OFF';
                
                // IMPORTANT: Hide WiFi Direct message FIRST
                hideWiFiDirectMessage();
                
                // Show the main section
                if (mainSection) mainSection.style.display = 'block';
                
                // Reset all tab states
                document.querySelectorAll('.tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                
                // Reset all tab content - HIDE all first
                document.querySelectorAll('.tab-content').forEach(content => {
                    content.classList.remove('active');
                });
                
                // Now properly activate ONLY the Available tab
                const availableTab = document.querySelector('[onclick="showTab(\'available\')"]');
                if (availableTab) availableTab.classList.add('active');
                
                // Show ONLY available section
                const availableSection = document.getElementById('available');
                if (availableSection) {
                    availableSection.classList.add('active');
                }
            }
        }


function hideWiFiDirectMessage() {
    const existingMessage = document.getElementById('wifi-direct-message');
    if (existingMessage) {
        existingMessage.remove();
    }
}

function showWiFiDirectMessage() {
    // Remove existing message if any
    hideWiFiDirectMessage();
    
    // Create WiFi Direct active message
    const container = document.querySelector('.container');
    const wifiDirectMessage = document.createElement('div');
    wifiDirectMessage.id = 'wifi-direct-message';
    wifiDirectMessage.className = 'wifi-direct-active-message';
    wifiDirectMessage.innerHTML = `
        <div class="wifi-direct-content">
            <div class="wifi-direct-icon">
                <i class="fas fa-broadcast-tower"></i>
            </div>
            <h3>WiFi Direct Mode Active</h3>
            <p>Device is in WiFi Direct mode. Network scanning and connection features are disabled.</p>
            <div class="wifi-direct-info">
                <div class="info-item">
                    <i class="fas fa-info-circle"></i>
                    <span>Other devices can connect directly to this device</span>
                </div>
            </div>
        </div>
    `;
    
    // Insert after the additional-section
    const additionalSection = document.querySelector('.additional-section');
    additionalSection.insertAdjacentElement('afterend', wifiDirectMessage);
}

async function fetchWiFiDirectStatus() {
    try {
        const response = await safeFetch(`get-wifi-direct`);
        const data = await response.json();
        wifiDirect = data.value === true;
        updateWiFiDirectUI(wifiDirect);
    } catch (error) {
        console.error('Error:', error);
        showToast('Error fetching WiFi Direct status', 'error', true);
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getSecurityBadgeClass(security) {
    if (!security || security === 'none' || security === 'open') {
        return 'badge-warning';
    }
    return 'badge-info';
}

function getSecurityIcon(security) {
    if (!security || security === 'none' || security === 'open') {
        return 'unlock';
    }
    return 'lock';
}

function getSecurityLabel(security) {
    if (!security || security === 'none' || security === 'open') {
        return 'Open';
    }
    return 'Secured';
}

// Close modal when clicking outside
document.getElementById('connect-modal').addEventListener('click', function(e) {
    if (e.target === this) {
        closeModal();
    }
});

// Prevent zoom on iOS when focusing input fields
document.addEventListener('touchstart', function() {}, {passive: true});

// Add mock data for local testing
window.mockNetworks = [
    { ssid: 'Home WiFi 5G', security: 'wpa2' },
    { ssid: 'Guest Network', security: 'open' },
    { ssid: 'Office Secure', security: 'wpa2' },
    { ssid: 'Cafe Free WiFi', security: 'open' },
    { ssid: 'Neighbor Network', security: 'wpa' }
];

// Override refreshNetworks for local testing when server is not available
const originalRefreshNetworks = window.refreshNetworks;
window.refreshNetworks = async function() {
    const container = document.getElementById('available-networks');
    
    // Try original first
    try {
        await originalRefreshNetworks();
    } catch (error) {
        // If server is not available, use mock data
        console.log('Using mock network data for testing');
        window.renderAvailableNetworks(window.mockNetworks);
    }
};
// Keyboard detection and modal repositioning
let keyboardHeight = 0;
let isKeyboardOpen = false;
let modalContent = null;
let originalModalPosition = null;

// Reposition modal above keyboard
function repositionModalForKeyboard() {
    const modal = document.getElementById('connect-modal');
    modalContent = document.querySelector('.modal-content');
    
    if (!modal || !modalContent) return;
    
    // Store original position if not stored
    if (!originalModalPosition) {
        originalModalPosition = {
            position: modalContent.style.position || '',
            bottom: modalContent.style.bottom || '',
            top: modalContent.style.top || '',
            left: modalContent.style.left || '',
            transform: modalContent.style.transform || '',
            maxHeight: modalContent.style.maxHeight || ''
        };
    }
    
    // Get the kioskboard element height directly
    const kioskboard = document.querySelector('#KioskBoard-VirtualKeyboard');
    let keyboardHeight = 0;
    
    if (kioskboard && kioskboard.offsetHeight > 0) {
        // Keyboard is visible
        keyboardHeight = kioskboard.offsetHeight;
    }
    
    if (keyboardHeight > 100) { // Keyboard is open
        isKeyboardOpen = true;
        
        // Force modal to be above keyboard
        modalContent.style.position = 'fixed';
        modalContent.style.bottom = (keyboardHeight + 20) + 'px'; // Add 20px padding
        modalContent.style.top = 'auto';
        modalContent.style.left = '50%';
        modalContent.style.transform = 'translateX(-50%)';
        modalContent.style.maxHeight = `${window.innerHeight - keyboardHeight - 20}px`;
        modalContent.style.zIndex = '9999';
    }
}

// Reset modal to original position
function resetModalPosition() {
    const modal = document.getElementById('connect-modal');
    if (!modalContent || !originalModalPosition) return;
    
    isKeyboardOpen = false;
    
    // Restore original styles
    modalContent.style.position = originalModalPosition.position;
    modalContent.style.bottom = originalModalPosition.bottom;
    modalContent.style.top = originalModalPosition.top;
    modalContent.style.left = originalModalPosition.left;
    modalContent.style.transform = originalModalPosition.transform;
    modalContent.style.maxHeight = originalModalPosition.maxHeight;
    modalContent.style.zIndex = '';
    
    originalModalPosition = null;
}
</script>
<!-- kioskboard -->
<link rel="stylesheet" href="./ui/public/static/css/kioskboard-2.3.0.min.css">
<script src="./ui/public/static/js/kioskboard-aio.min.js"></script>
<script>
// Initialize KioskBoard when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize kioskboard for password inputs
    window.initKeyboardForModal = function() {
        const passwordInput = document.querySelector('#connect-password');
        
        // Check if already initialized
        if (passwordInput && !passwordInput._kioskBoardInitialized) {
            KioskBoard.run('.connect-password', {
                theme: 'dark',
                capsLockActive: false,
                allowRealKeyboard: true,
                allowMobileKeyboard: false,
                cssAnimations: true,
                cssAnimationsDuration: 360,
                cssAnimationsStyle: 'slide',
                keysArrayOfObjects: null,
                keysJsonUrl: null,
                keysSpecialCharsArrayOfStrings: ['!', '#', '$', '%', '&', '*', '+', '-', '=', '?', '@', '^', '_', '|', '~'],
                keysNumpadArrayOfNumbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 0],
                language: 'en',
                autoScroll: false,
                
                // Callback when keyboard opens
                onShow: function() {
                    setTimeout(() => {
                        repositionModalForKeyboard();
                    }, 100);
                },
                
                // Callback when keyboard closes
                onHide: function() {
                    setTimeout(() => {
                        resetModalPosition();
                    }, 100);
                }
            });
            passwordInput._kioskBoardInitialized = true;
            
            // Also use MutationObserver as a fallback to detect keyboard
            const observer = new MutationObserver(function(mutations) {
                const kioskboard = document.querySelector('#KioskBoard-VirtualKeyboard');
                if (kioskboard) {
                    // Check if keyboard is visible
                    const isVisible = kioskboard.style.visibility !== 'hidden' && 
                                    kioskboard.style.display !== 'none' &&
                                    kioskboard.offsetHeight > 0;
                    
                    if (isVisible) {
                        // Keyboard appeared, reposition modal
                        setTimeout(() => {
                            repositionModalForKeyboard();
                        }, 200);
                    }
                }
            });
            
            // Start observing the body for changes
            observer.observe(document.body, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ['style', 'class']
            });
            
            // Store observer to disconnect later if needed
            window._kioskboardObserver = observer;
        }
    };
});

