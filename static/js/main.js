document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const body = document.getElementById('app-body');
    const roiSlider = document.getElementById('roi-slider');
    const roiValue = document.getElementById('roi-value');
    const btnScan = document.getElementById('btn-scan');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const statusText = document.getElementById('status-text');
    const statusDot = document.getElementById('status-dot');
    const deviceName = document.getElementById('device-name');
    const resultContainer = document.getElementById('result-container');
    const placeholderView = document.getElementById('placeholder-view');
    const mapsGrid = document.getElementById('maps-grid');
    const historyGrid = document.getElementById('history-grid');
    const btnRefreshHistory = document.getElementById('refresh-history');

    // New Elements
    const deviceRadios = document.querySelectorAll('input[name="device"]');
    const scanBoxCheckbox = document.getElementById('scan-box-mode');
    const focusStackCheckbox = document.getElementById('focus-stack-mode');
    const roiBtns = document.querySelectorAll('.roi-btn');
    
    // Live Preview Elements
    const btnLivePreview = document.getElementById('btn-live-preview');
    const previewModal = document.getElementById('preview-modal');
    const previewModalContent = document.getElementById('preview-modal-content');
    const btnClosePreview = document.getElementById('btn-close-preview');
    const btnRefreshPreview = document.getElementById('btn-refresh-preview');
    const previewCanvas = document.getElementById('preview-canvas');
    const loadingPreview = document.getElementById('loading-preview');
    const btnConfirmRoi = document.getElementById('btn-confirm-roi');
    const btnClearRoi = document.getElementById('btn-clear-roi');
    const previewRoiInfo = document.getElementById('preview-roi-info');

    // Camera Settings Elements
    const cameraSettings = document.getElementById('camera-settings');
    const deviceInfo = document.getElementById('device-info');
    const infoImageSize = document.getElementById('info-imagesize');
    const camIso = document.getElementById('cam-iso');
    const camAperture = document.getElementById('cam-aperture');
    const camShutter = document.getElementById('cam-shutter');
    const camImageSize = document.getElementById('cam-imagesize');
    
    // PBR Adjustment Elements (Sidebar)
    const paramNormalStrength = document.getElementById('param-normal-strength');
    const paramRoughnessMin = document.getElementById('param-roughness-min');
    const paramRoughnessMax = document.getElementById('param-roughness-max');
    const paramDispContrast = document.getElementById('param-disp-contrast');
    
    // UI Helpers for Sliders
    function linkSliderToValue(sliderId, valueId) {
        const slider = document.getElementById(sliderId);
        const display = document.getElementById(valueId);
        if (slider && display) {
            slider.addEventListener('input', (e) => {
                display.textContent = e.target.value;
            });
        }
    }

    linkSliderToValue('param-normal-strength', 'val-normal-strength');
    linkSliderToValue('param-disp-contrast', 'val-disp-contrast');
    linkSliderToValue('reprocess-normal-strength', 'reprocess-val-normal');
    linkSliderToValue('reprocess-disp-contrast', 'reprocess-val-disp');
    
    // Reprocess Modal Elements
    const reprocessModal = document.getElementById('reprocess-modal');
    const btnCloseReprocess = document.getElementById('btn-close-reprocess');
    const btnCancelReprocess = document.getElementById('btn-cancel-reprocess');
    const btnConfirmReprocess = document.getElementById('btn-confirm-reprocess');
    const reprocessFilename = document.getElementById('reprocess-filename');
    
    // Reprocess Params
    const reprocessNormalStrength = document.getElementById('reprocess-normal-strength');
    const reprocessRoughnessMin = document.getElementById('reprocess-roughness-min');
    const reprocessRoughnessMax = document.getElementById('reprocess-roughness-max');
    const reprocessDispContrast = document.getElementById('reprocess-disp-contrast');

    let roiOffset = { x: 0, y: 0 };
    let roiSelection = null; // { x, y, w, h } in percentages (0.0 to 1.0)

    // Tab Elements
    const tabs = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    // 3D Viewer Elements
    let scene, camera, renderer, mesh, controls, mainLight;
    let currentTextureMaps = {};

    // Theme Management
    function setTheme(theme) {
        body.classList.remove('theme-leica', 'theme-nikon');
        if (theme === 'leica-red') {
            body.classList.add('theme-leica');
        } else if (theme === 'nikon-blue') {
            body.classList.add('theme-nikon');
        }
    }

    // ROI Position Logic
    roiBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const dir = btn.dataset.dir;
            const step = 5; // 5% shift
            if (dir === 'up') roiOffset.y -= step;
            if (dir === 'down') roiOffset.y += step;
            if (dir === 'left') roiOffset.x -= step;
            if (dir === 'right') roiOffset.x += step;
            
            // Visual feedback (optional)
            console.log('ROI Offset:', roiOffset);
            
            // Blink effect
            btn.classList.add('bg-slate-600');
            setTimeout(() => btn.classList.remove('bg-slate-600'), 100);
        });
    });

    // Tab Switching
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active', 'tab-active'));
            tabContents.forEach(c => c.classList.add('hidden'));
            
            tab.classList.add('active', 'tab-active');
            const tabId = `tab-${tab.dataset.tab}`;
            document.getElementById(tabId).classList.remove('hidden');

            if (tab.dataset.tab === 'history') {
                loadHistory();
                setTimeout(() => {
                    init3D();
                    onWindowResize();
                }, 100);
            }
        });
    });

    // Initial Check
    // Initialize theme based on default checked radio
    const defaultDevice = document.querySelector('input[name="device"]:checked').value;
    if (defaultDevice === 'mi13') setTheme('leica-red');
    if (defaultDevice === 'z30') setTheme('nikon-blue');

    let isScanning = false; // Track scanning state
    const disconnectToast = document.getElementById('disconnect-toast');
    let scanPollInterval = null; // Store polling interval to clear it

    checkDeviceStatus();
    setInterval(checkDeviceStatus, 5000); // Poll every 5s

    async function checkDeviceStatus() {
        try {
            const deviceType = document.querySelector('input[name="device"]:checked').value;
            const res = await fetch(`/api/status?device=${deviceType}`);
            const data = await res.json();
            
            if (data.connected) {
                statusDot.classList.remove('bg-gray-500', 'bg-red-500');
                statusDot.classList.add('bg-green-500');
                deviceName.textContent = data.device;
                
                // Hide Toast
                disconnectToast.classList.add('hidden');
            } else {
                statusDot.classList.remove('bg-green-500');
                statusDot.classList.add('bg-gray-500');
                deviceName.textContent = "Disconnected";

                // Show Toast
                disconnectToast.classList.remove('hidden');

                // Stop Scan if running
                if (isScanning) {
                    console.warn("Device disconnected during scan. Aborting...");
                    abortScan("Device Disconnected");
                }
            }
        } catch (e) {
            console.error("Status check failed", e);
        }
    }
    
    function abortScan(reason) {
        if (!isScanning) return;
        
        isScanning = false;
        
        // Stop polling
        if (scanPollInterval) {
            clearInterval(scanPollInterval);
            scanPollInterval = null;
        }

        // Reset UI
        alert(`Scan Aborted: ${reason}`);
        statusText.textContent = `Aborted: ${reason}`;
        resetScanUI();
    }

    // UI Interactions
    deviceRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            if (e.target.value === 'mi13') {
                setTheme('leica-red');
                if (cameraSettings) cameraSettings.classList.add('hidden');
                if (deviceInfo) {
                    deviceInfo.classList.remove('hidden');
                    fetchDeviceInfo();
                }
            } else if (e.target.value === 'z30') {
                setTheme('nikon-blue');
                if (cameraSettings) cameraSettings.classList.remove('hidden');
                if (deviceInfo) deviceInfo.classList.add('hidden');
                fetchCameraConfig(); // Load current settings
            }
            checkDeviceStatus(); // Check status immediately on switch
        });
    });

    // Device Info for Mi 13
    async function fetchDeviceInfo() {
        try {
            const res = await fetch('/api/camera/config?device=mi13&config=imagesize');
            const data = await res.json();
            if (infoImageSize) {
                infoImageSize.textContent = data.value || "Unknown";
            }
        } catch (e) {
            console.error("Failed to load device info", e);
        }
    }

    // Camera Configuration Logic
    async function fetchCameraConfig() {
        try {
            const res = await fetch('/api/camera/config?device=z30');
            const data = await res.json();
            if (data.iso && camIso) camIso.value = data.iso;
            if (data.aperture && camAperture) camAperture.value = data.aperture;
            if (data.shutterspeed && camShutter) camShutter.value = data.shutterspeed;
            
            // Handle Image Size (Parse string "Current (Options: ...)")
            if (data.imagesize && camImageSize) {
                // Clear existing
                camImageSize.innerHTML = '';
                
                const raw = data.imagesize;
                // Format: "Large (Options: Large, Medium, Small)" or just "Large"
                let current = raw;
                let options = [raw];
                
                if (raw.includes("(Options:")) {
                    const parts = raw.split("(Options:");
                    current = parts[0].trim();
                    const optsStr = parts[1].replace(')', '').trim();
                    options = optsStr.split(',').map(s => s.trim());
                }
                
                // Populate
                options.forEach(opt => {
                    const el = document.createElement('option');
                    el.value = opt;
                    el.textContent = opt;
                    if (opt === current) el.selected = true;
                    camImageSize.appendChild(el);
                });
            }
        } catch (e) {
            console.error("Failed to load camera config", e);
        }
    }

    async function setCameraConfig(config, value) {
        try {
            const res = await fetch('/api/camera/config?device=z30', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config, value })
            });
            const data = await res.json();
            if (!data.success) {
                console.error("Failed to set config", data.error);
                // Revert UI if failed (optional, for now just log)
            } else {
                console.log(data.message);
            }
        } catch (e) {
            console.error("Error setting config", e);
        }
    }

    if (camIso) {
        camIso.addEventListener('change', (e) => setCameraConfig('iso', e.target.value));
        camAperture.addEventListener('change', (e) => setCameraConfig('aperture', e.target.value));
        camShutter.addEventListener('change', (e) => setCameraConfig('shutterspeed', e.target.value));
    }

    roiSlider.addEventListener('input', (e) => {
        roiValue.textContent = `${e.target.value} x ${e.target.value} cm`;
    });

    // Scanning Logic
    btnScan.addEventListener('click', async () => {
        // UI Loading State
        isScanning = true;
        btnScan.disabled = true;
        btnScan.classList.add('opacity-50', 'cursor-not-allowed');
        progressContainer.classList.remove('hidden');
        progressBar.style.width = '0%';
        statusText.textContent = "Starting...";
        
        // Get Name
        const materialName = document.getElementById('scan-name').value;
        const materialTags = document.getElementById('scan-tags').value;

        // Get selected maps
        const selectedMaps = Array.from(document.querySelectorAll('.map-checkbox:checked')).map(cb => cb.value);

        // Get Scan Settings
        const deviceType = document.querySelector('input[name="device"]:checked').value;
        const useScanBox = document.getElementById('scan-box-mode').checked;
        const useFocusStack = document.getElementById('focus-stack-mode') ? document.getElementById('focus-stack-mode').checked : false;

        // Determine Scan Mode
        let scanMode = 'single';
        if (useScanBox) scanMode = 'photometric';
        else if (useFocusStack) scanMode = 'focus_stack';

        try {
            // API Call
            const response = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    roi_size: parseInt(roiSlider.value),
                    maps: selectedMaps,
                    device_type: deviceType,
                    scan_mode: scanMode,
                    roi_offset: roiOffset,
                    roi_rect: roiSelection,
                    name: materialName,
                    tags: materialTags
                })
            });

            const result = await response.json();

            if (result.task_id) {
                // Start polling
                pollProgress(result.task_id, (finalResult) => {
                    isScanning = false;
                    displayResults(finalResult.maps);
                    loadHistory();
                    statusText.textContent = "Processing complete";
                    resetScanUI();
                }, (error) => {
                    isScanning = false;
                    alert('Error: ' + error);
                    statusText.textContent = "Error occurred";
                    resetScanUI();
                });
            } else if (result.error) {
                isScanning = false;
                alert('Error: ' + result.error);
                statusText.textContent = "Error occurred";
                resetScanUI();
            }

        } catch (error) {
            console.error(error);
            isScanning = false;
            alert('Network Error');
            statusText.textContent = "Network Error";
            resetScanUI();
        }
    });

    function resetScanUI() {
        setTimeout(() => {
            progressContainer.classList.add('hidden');
            progressBar.style.width = '0%';
            btnScan.disabled = false;
            btnScan.classList.remove('opacity-50', 'cursor-not-allowed');
        }, 1000);
    }

    function pollProgress(taskId, onSuccess, onError) {
        scanPollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/progress/${taskId}`);
                const data = await res.json();
                
                if (data.error) {
                    clearInterval(scanPollInterval);
                    scanPollInterval = null;
                    onError(data.error);
                    return;
                }

                // Update UI
                progressBar.style.width = `${data.percent}%`;
                statusText.textContent = data.message;

                if (data.status === 'completed') {
                    clearInterval(scanPollInterval);
                    scanPollInterval = null;
                    onSuccess(data.result); // result should be in the task data
                } else if (data.status === 'failed') {
                    clearInterval(scanPollInterval);
                    scanPollInterval = null;
                    onError(data.error || "Task failed");
                }
            } catch (e) {
                console.error("Polling error", e);
                // Don't stop polling immediately on network glitch, but maybe count errors?
            }
        }, 1000);
    }

    function displayResults(maps) {
        placeholderView.classList.add('hidden');
        mapsGrid.classList.remove('hidden');
        mapsGrid.innerHTML = '';

        const mapTypes = [
            { key: 'base_color', label: 'Base Color' },
            { key: 'normal', label: 'Normal Map' },
            { key: 'roughness', label: 'Roughness' },
            { key: 'displacement', label: 'Displacement' },
            { key: 'ao', label: 'Ambient Occlusion' },
            { key: 'metallic', label: 'Metallic' },
        ];

        mapTypes.forEach(type => {
            if (maps[type.key]) {
                const card = document.createElement('div');
                card.className = "bg-slate-900 border border-slate-800 rounded-lg overflow-hidden group hover:border-slate-600 transition-colors";
                card.innerHTML = `
                    <div class="aspect-square bg-slate-950 relative overflow-hidden">
                        <img src="${maps[type.key]}?t=${new Date().getTime()}" class="w-full h-full object-cover" alt="${type.label}">
                        <div class="absolute bottom-0 left-0 right-0 bg-black/70 p-2 transform translate-y-full group-hover:translate-y-0 transition-transform">
                            <span class="text-xs text-white">${type.label}</span>
                        </div>
                    </div>
                    <div class="p-2 flex justify-between items-center">
                        <span class="text-xs text-slate-400">${type.label}</span>
                        <a href="${maps[type.key]}" download class="text-slate-500 hover:text-white"><i data-lucide="download" class="w-4 h-4"></i></a>
                    </div>
                `;
                mapsGrid.appendChild(card);
            }
        });
        
        lucide.createIcons();
    }

    // History Logic
    let historyData = []; // Store full history
    let currentViewMode = 'grid'; // 'grid' or 'list'

    btnRefreshHistory.addEventListener('click', loadHistory);
    
    // Search & Filter Elements
    const historySearch = document.getElementById('history-search');
    const btnFilter = document.getElementById('btn-filter');
    const filterPopover = document.getElementById('filter-popover');
    const filterTags = document.getElementById('filter-tags');
    const filterDate = document.getElementById('filter-date');
    const btnViewGrid = document.getElementById('view-grid');
    const btnViewList = document.getElementById('view-list');

    // Toggle Filter Popover
    if(btnFilter) {
        btnFilter.addEventListener('click', (e) => {
            e.stopPropagation();
            filterPopover.classList.toggle('hidden');
        });
        // Close when clicking outside
        document.addEventListener('click', (e) => {
             if (filterPopover && !filterPopover.contains(e.target) && !btnFilter.contains(e.target)) {
                 filterPopover.classList.add('hidden');
             }
        });
    }

    // View Mode Switching
    // (Removed View Mode Switching as we enforce 3-Pane Layout)

    function renderHistory() {
        const container = document.getElementById('history-list-container');
        if (!container) return;
        
        container.innerHTML = '';
        
        const searchTerm = historySearch ? historySearch.value.toLowerCase() : '';
        const tagTerm = filterTags ? filterTags.value.toLowerCase() : '';
        const dateFilter = filterDate ? filterDate.value : 'all';

        const filtered = historyData.filter(item => {
            const matchName = item.name.toLowerCase().includes(searchTerm);
            const itemTags = item.tags || [];
            const matchTagsSearch = itemTags.some(t => t.toLowerCase().includes(searchTerm));
            
            let matchFilterTag = true;
            if (tagTerm) {
                matchFilterTag = itemTags.some(t => t.toLowerCase().includes(tagTerm));
            }
            
            let matchDate = true;
            if (dateFilter !== 'all') {
                const itemDate = new Date(item.created_at * 1000);
                const now = new Date();
                const diffTime = Math.abs(now - itemDate);
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                
                if (dateFilter === 'today' && diffDays > 1) matchDate = false;
                if (dateFilter === 'week' && diffDays > 7) matchDate = false;
                if (dateFilter === 'month' && diffDays > 30) matchDate = false;
            }
            
            return (matchName || matchTagsSearch) && matchFilterTag && matchDate;
        });

        if (filtered.length === 0) {
            container.innerHTML = '<div class="text-center text-slate-500 text-sm mt-4">No items found</div>';
            return;
        }

        filtered.forEach(item => {
            const dateStr = new Date(item.created_at * 1000).toLocaleDateString();
            const el = document.createElement('div');
            el.className = "p-2 rounded bg-slate-800 border border-slate-700 hover:border-slate-500 cursor-pointer transition-colors group history-item";
            el.dataset.id = item.id; // Assuming ID is unique, or use index if needed
            
            // Thumbnail (Base Color)
            const thumbUrl = item.maps.base_color || item.maps.diffuse || '';
            
            el.innerHTML = `
                <div class="flex gap-3 items-center">
                    <div class="w-12 h-12 bg-slate-900 rounded overflow-hidden shrink-0 border border-slate-700">
                        ${thumbUrl ? `<img src="${thumbUrl}" class="w-full h-full object-cover">` : '<div class="w-full h-full flex items-center justify-center"><i data-lucide="image" class="w-4 h-4 text-slate-600"></i></div>'}
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="font-bold text-sm text-white truncate group-hover:text-blue-400 transition-colors">${item.name}</div>
                        <div class="text-xs text-slate-500 flex items-center gap-2">
                            <span>${dateStr}</span>
                            ${item.tags && item.tags.length ? `<span class="bg-slate-700 px-1 rounded text-[10px] text-slate-300">${item.tags[0]}</span>` : ''}
                        </div>
                    </div>
                </div>
            `;
            
            el.addEventListener('click', () => selectHistoryItem(item, el));
            container.appendChild(el);
        });
        
        lucide.createIcons();
    }

    function selectHistoryItem(item, element) {
        // 1. Highlight Selection
        document.querySelectorAll('.history-item').forEach(el => el.classList.remove('bg-slate-700', 'border-blue-500'));
        element.classList.add('bg-slate-700', 'border-blue-500');
        element.classList.remove('bg-slate-800', 'border-slate-700');

        // 2. Update Maps Preview
        updateMapsPreview(item);

        // 3. Update 3D Preview
        update3DPreview(item);
    }

    function updateMapsPreview(item) {
        const container = document.getElementById('maps-preview-container');
        if (!container) return;
        
        container.innerHTML = '';
        
        const mapTypes = [
            { key: 'base_color', label: 'Base Color' },
            { key: 'normal', label: 'Normal' },
            { key: 'roughness', label: 'Roughness' },
            { key: 'displacement', label: 'Displacement' },
            { key: 'ao', label: 'AO' },
            { key: 'metallic', label: 'Metallic' }
        ];

        const grid = document.createElement('div');
        grid.className = "grid grid-cols-2 gap-3";

        mapTypes.forEach(type => {
            if (item.maps[type.key]) {
                const card = document.createElement('div');
                card.className = "bg-slate-900 border border-slate-800 rounded overflow-hidden group hover:border-slate-600 transition-colors";
                
                // Create inner content
                const inner = document.createElement('div');
                inner.className = "aspect-square bg-slate-950 relative overflow-hidden cursor-pointer";
                inner.innerHTML = `
                    <img src="${item.maps[type.key]}" class="w-full h-full object-cover" alt="${type.label}">
                    <div class="absolute bottom-0 left-0 right-0 bg-black/70 p-1 transform translate-y-full group-hover:translate-y-0 transition-transform">
                        <span class="text-[10px] text-white">${type.label}</span>
                    </div>
                `;
                inner.onclick = () => window.open(item.maps[type.key], '_blank');
                
                card.appendChild(inner);
                grid.appendChild(card);
            }
        });
        
        // Add "Open Folder" or "Reprocess" actions if needed
        const actions = document.createElement('div');
        actions.className = "mt-4 flex gap-2 justify-center";
        actions.innerHTML = `
             <button class="px-3 py-1 bg-slate-800 hover:bg-slate-700 rounded text-xs border border-slate-700" onclick="alert('Reprocess feature coming soon')">
                <i data-lucide="refresh-cw" class="w-3 h-3 inline mr-1"></i> Reprocess
             </button>
             <a href="/api/download/${item.id}" target="_blank" class="px-3 py-1 bg-blue-900/50 hover:bg-blue-900 rounded text-xs border border-blue-800 text-blue-200">
                <i data-lucide="download" class="w-3 h-3 inline mr-1"></i> Download All
             </a>
        `;
        
        container.appendChild(grid);
        container.appendChild(actions);
        lucide.createIcons();
    }


    // Filter Inputs
    if (historySearch) historySearch.addEventListener('input', renderHistory);
    if (filterTags) filterTags.addEventListener('input', renderHistory);
    if (filterDate) filterDate.addEventListener('change', renderHistory);

    const previewMaterialSelect = document.getElementById('preview-material-select');
    if (previewMaterialSelect) {
        previewMaterialSelect.addEventListener('change', (e) => {
            if (e.target.value) {
                load3DView(e.target.value);
            }
        });
    }

    async function loadHistory() {
        try {
            const res = await fetch('/api/history');
            historyData = await res.json();
            
            // Populate Dropdown
            if (previewMaterialSelect) {
                previewMaterialSelect.innerHTML = '<option value="">-- Select from History --</option>';
                historyData.forEach(item => {
                    const option = document.createElement('option');
                    option.value = item.folder_name;
                    option.textContent = item.name;
                    previewMaterialSelect.appendChild(option);
                });
            }

            renderHistory();
        } catch (e) {
            console.error("Failed to load history", e);
        }
    }

    // History List Render (3-Pane Layout)
    // Duplicate renderHistory removed.

    
    // Global functions for inline onclick
    window.preview3D = function(folderName) {
        load3DView(folderName);
        if(previewMaterialSelect) previewMaterialSelect.value = folderName;
    };
    
    window.downloadU3M = async function(folderName) {
         try {
            const res = await fetch('/api/export/u3m', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: folderName }) // API expects filename/folder
            });
            const data = await res.json();
            if(data.success) {
                const a = document.createElement('a');
                a.href = data.download_url;
                a.download = '';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            } else {
                alert('Export failed: ' + data.error);
            }
        } catch(e) {
            alert('Export error');
        }
    };
    
    // Reprocess Modal Logic
    function openReprocessModal(filename) {
        reprocessFilename.textContent = filename;
        reprocessModal.classList.remove('hidden');
        reprocessModal.classList.add('flex'); // Ensure flex is added
        
        // Reset defaults or load previous if we had them (optional)
        // For now reset to defaults
        reprocessNormalStrength.value = 1.0;
        reprocessRoughnessMin.value = 0;
        reprocessRoughnessMax.value = 255;
        reprocessDispContrast.value = 1.0;
        
        // Store filename on the confirm button for easy access
        btnConfirmReprocess.dataset.filename = filename;
    }
    
    if (btnCloseReprocess) {
        btnCloseReprocess.addEventListener('click', () => {
            reprocessModal.classList.add('hidden');
        });
    }
    
    if (btnCancelReprocess) {
        btnCancelReprocess.addEventListener('click', () => {
            reprocessModal.classList.add('hidden');
        });
    }
    
    if (btnConfirmReprocess) {
        btnConfirmReprocess.addEventListener('click', async () => {
            const filename = btnConfirmReprocess.dataset.filename;
            
            // Collect params
            const params = {
                normal_strength: parseFloat(reprocessNormalStrength.value),
                roughness_min: parseInt(reprocessRoughnessMin.value),
                roughness_max: parseInt(reprocessRoughnessMax.value),
                displacement_contrast: parseFloat(reprocessDispContrast.value)
            };
            
            // Check which maps are selected
            const mapsToProcess = Array.from(document.querySelectorAll('.reprocess-map-check:checked')).map(cb => cb.value);
            
            if (mapsToProcess.length === 0) {
                alert("Please select at least one map to process.");
                return;
            }
            
            // UI Feedback
            btnConfirmReprocess.textContent = "Processing...";
            btnConfirmReprocess.disabled = true;
            reprocessModal.classList.add('hidden'); // Hide modal to show progress in footer
            showProgressUI("Starting reprocessing...");
            
            try {
                const res = await fetch('/api/reprocess', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        filename: filename,
                        maps: mapsToProcess,
                        params: params
                    })
                });
                const data = await res.json();
                
                if (data.task_id) {
                    pollProgress(data.task_id, () => {
                        // Success
                        alert("Reprocessed successfully!");
                        loadHistory();
                        statusText.textContent = "Reprocessing complete";
                        hideProgressUI();
                        
                        btnConfirmReprocess.textContent = "Reprocess";
                        btnConfirmReprocess.disabled = false;
                    }, (error) => {
                         alert("Error: " + error);
                         statusText.textContent = "Error occurred";
                         hideProgressUI();
                         
                         btnConfirmReprocess.textContent = "Reprocess";
                         btnConfirmReprocess.disabled = false;
                    });
                } else {
                    alert("Error: " + (data.error || "Unknown error"));
                    hideProgressUI();
                    btnConfirmReprocess.textContent = "Reprocess";
                    btnConfirmReprocess.disabled = false;
                }
            } catch(err) {
                console.error(err);
                alert("Error reprocessing");
                hideProgressUI();
                btnConfirmReprocess.textContent = "Reprocess";
                btnConfirmReprocess.disabled = false;
            }
        });
    }

    // Obsolete listeners for old 3D tab removed


    // New 3D Preview Controls Listeners
    const previewNormalStrength = document.getElementById('preview-normal-strength');
    if (previewNormalStrength) {
        previewNormalStrength.addEventListener('input', (e) => {
             const val = parseFloat(e.target.value);
             if (mesh && mesh.material) mesh.material.normalScale.set(val, val);
        });
    }

    const previewDispScale = document.getElementById('preview-disp-scale');
    if (previewDispScale) {
        previewDispScale.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value);
            if (mesh && mesh.material && mesh.material.displacementMap) {
                mesh.material.displacementScale = 0.1 * val;
            }
        });
    }
    
    const previewLightIntensity = document.getElementById('preview-light-intensity');
    if (previewLightIntensity) {
        previewLightIntensity.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value);
            if (mainLight) mainLight.intensity = val;
        });
    }

    function init3D() {
        if (scene) return; // Already initialized

        const container = document.getElementById('canvas-container');
        scene = new THREE.Scene();
        scene.background = new THREE.Color(0x111111);

        camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 100);
        camera.position.z = 3;

        renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(container.clientWidth, container.clientHeight);
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.outputEncoding = THREE.sRGBEncoding;
        container.appendChild(renderer.domElement);

        controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;

        // Lights
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.2);
        scene.add(ambientLight);

        mainLight = new THREE.DirectionalLight(0xffffff, 1);
        mainLight.position.set(3.5, 5, 3.5); // 45 deg approx
        scene.add(mainLight);
        
        // Fill light
        const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
        fillLight.position.set(-3, 2, -3);
        scene.add(fillLight);

        // Initial Mesh
        updateGeometry('sphere');

        // Animation Loop
        function animate() {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        }
        animate();
    }
    
    // PBR Param Listeners for 3D View (Realtime Preview)
    const pbrNormalStrength = document.getElementById('param-normal-strength');
    if (pbrNormalStrength) {
        pbrNormalStrength.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value);
            document.getElementById('val-normal-strength').textContent = val;
            if (mesh && mesh.material) {
                // Update normal scale visual
                mesh.material.normalScale.set(val, val);
            }
        });
    }

    const pbrDispContrast = document.getElementById('param-disp-contrast');
    if (pbrDispContrast) {
        pbrDispContrast.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value);
            document.getElementById('val-disp-contrast').textContent = val;
            if (mesh && mesh.material) {
                // Update displacement scale visual (approximate contrast effect)
                // Default scale is usually around 0.1 or 0.2 depending on map
                // We use this slider to multiplier
                const baseScale = 0.1; 
                mesh.material.displacementScale = baseScale * val;
            }
        });
    }

    const pbrRoughnessMin = document.getElementById('param-roughness-min');
    const pbrRoughnessMax = document.getElementById('param-roughness-max');
    
    // Roughness update helper (requires shader mod or just re-upload texture? 
    // StandardMaterial can't remap roughness texture easily.
    // For now, we just update the text, maybe in future use onBeforeCompile)
    if (pbrRoughnessMin) {
        pbrRoughnessMin.addEventListener('input', () => {
           // No realtime preview for roughness remapping yet
        });
    }

    // Light Controls
    const lightIntensitySlider = document.getElementById('light-intensity');
    if (lightIntensitySlider) {
        lightIntensitySlider.addEventListener('input', (e) => {
            const val = parseFloat(e.target.value);
            document.getElementById('light-intensity-val').textContent = val;
            if (mainLight) mainLight.intensity = val;
        });
    }

    const lightRotSlider = document.getElementById('light-rot');
    if (lightRotSlider) {
        lightRotSlider.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            document.getElementById('light-rot-val').textContent = val + "°";
            if (mainLight) {
                const rad = val * (Math.PI / 180);
                const r = 5; // Radius
                mainLight.position.x = Math.sin(rad) * r;
                mainLight.position.z = Math.cos(rad) * r;
            }
        });
    }

    function updateGeometry(type) {
        // Preserve material if it exists (to keep loaded textures)
        let material;
        if (mesh && mesh.material) {
            material = mesh.material;
            scene.remove(mesh);
            mesh.geometry.dispose();
        } else {
            material = new THREE.MeshStandardMaterial({ 
                color: 0x888888,
                roughness: 0.5,
                metalness: 0.0,
                side: THREE.DoubleSide
            });
        }
        
        // Sync material params with UI if possible
        if (pbrNormalStrength) {
            const val = parseFloat(pbrNormalStrength.value);
            material.normalScale.set(val, val);
        }
        if (pbrDispContrast) {
            const val = parseFloat(pbrDispContrast.value);
            material.displacementScale = 0.1 * val;
        }

        let geometry;
        if (type === 'sphere') {
            geometry = new THREE.SphereGeometry(1, 128, 128);
        } else if (type === 'plane') {
            geometry = new THREE.PlaneGeometry(2, 2, 128, 128);
        } else if (type === 'cube') {
            geometry = new THREE.BoxGeometry(1.5, 1.5, 1.5, 64, 64, 64);
        }

        mesh = new THREE.Mesh(geometry, material);
        scene.add(mesh);
    }

    // Geometry Select Listener
    const geoSelect = document.getElementById('geometry-select');
    if (geoSelect) {
        geoSelect.addEventListener('change', (e) => {
            updateGeometry(e.target.value);
        });
    }

    function onWindowResize() {
        if (!camera || !renderer) return;
        const container = document.getElementById('canvas-container');
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    }
    window.addEventListener('resize', onWindowResize);

    function update3DPreview(item) {
        // Ensure 3D is initialized
        if (!scene) init3D();
        
        // Resize just in case (e.g. if tab was hidden)
        onWindowResize();

        const maps = item.maps || {};
        
        const textureLoader = new THREE.TextureLoader();
        
        // Reset material
        if (mesh && mesh.material) {
            // Dispose old textures to free memory (optional but good practice)
            if (mesh.material.map) mesh.material.map.dispose();
            if (mesh.material.normalMap) mesh.material.normalMap.dispose();
            if (mesh.material.roughnessMap) mesh.material.roughnessMap.dispose();
            if (mesh.material.displacementMap) mesh.material.displacementMap.dispose();
            if (mesh.material.aoMap) mesh.material.aoMap.dispose();
            if (mesh.material.metalnessMap) mesh.material.metalnessMap.dispose();

            mesh.material.map = null;
            mesh.material.normalMap = null;
            mesh.material.roughnessMap = null;
            mesh.material.displacementMap = null;
            mesh.material.aoMap = null;
            mesh.material.metalnessMap = null;
            mesh.material.needsUpdate = true;
        }
        
        // Helper to load texture
        const loadTex = (type, path) => {
            if (!path) return;
            
            // Add timestamp to avoid caching issues during session
            // const url = path + '?t=' + new Date().getTime(); 
            // Better to rely on browser cache unless updated
            
            textureLoader.load(path, (tex) => {
                tex.wrapS = THREE.RepeatWrapping;
                tex.wrapT = THREE.RepeatWrapping;
                
                if (!mesh || !mesh.material) return;

                if (type === 'base_color') mesh.material.map = tex;
                if (type === 'normal') mesh.material.normalMap = tex;
                if (type === 'roughness') mesh.material.roughnessMap = tex;
                if (type === 'displacement') {
                    mesh.material.displacementMap = tex;
                    const dispEl = document.getElementById('preview-disp-scale');
                    const dispVal = dispEl ? dispEl.value : 1;
                    mesh.material.displacementScale = 0.1 * parseFloat(dispVal);
                }
                if (type === 'ao') mesh.material.aoMap = tex;
                if (type === 'metallic') mesh.material.metalnessMap = tex;
                
                mesh.material.needsUpdate = true;
            }, undefined, (err) => {
                console.warn(`Failed to load ${type} from ${path}`, err);
            });
        };
        
        // Load what we have
        loadTex('base_color', maps.base_color || maps.diffuse);
        loadTex('normal', maps.normal);
        loadTex('roughness', maps.roughness);
        loadTex('displacement', maps.displacement || maps.height);
        loadTex('ao', maps.ao || maps.ambient_occlusion);
        loadTex('metallic', maps.metallic);
    }

    function load3DView(folderName) {
        // Switch to History tab (where 3D is now located)
        const historyTab = document.querySelector('[data-tab="history"]');
        if(historyTab) historyTab.click();
        
        // Find item in history to get exact map paths
        const item = historyData.find(i => i.folder_name === folderName);
        
        if (item) {
            update3DPreview(item);
        } else {
            // Fallback for direct access or legacy: try to construct paths
            console.warn("Item not found in history, trying legacy path construction");
            const maps = {
                base_color: `/scans/${folderName}/${folderName}_BaseColor.jpg`,
                normal: `/scans/${folderName}/${folderName}_Normal.png`,
                roughness: `/scans/${folderName}/${folderName}_Roughness.jpg`,
                displacement: `/scans/${folderName}/${folderName}_Displacement.jpg`,
                ao: `/scans/${folderName}/${folderName}_AO.jpg`,
                metallic: `/scans/${folderName}/${folderName}_Metallic.jpg`
            };
            update3DPreview({ maps });
        }
    }
    
    // Obsolete displacement slider listener removed


    // ==========================================
    // Live Preview & ROI Logic
    // ==========================================
    
    let isDrawing = false;
    let startX = 0;
    let startY = 0;
    let currentRect = null; // {x, y, w, h} in pixels
    let previewImage = null; // Image object

    if (btnLivePreview) {
        btnLivePreview.addEventListener('click', () => {
            previewModal.classList.remove('hidden');
            loadPreview();
        });
    }

    if (btnClosePreview) {
        btnClosePreview.addEventListener('click', closePreviewModal);
    }

    if (btnRefreshPreview) {
        btnRefreshPreview.addEventListener('click', loadPreview);
    }

    if (btnClearRoi) {
        btnClearRoi.addEventListener('click', () => {
            currentRect = null;
            roiSelection = null;
            drawPreviewCanvas();
            previewRoiInfo.textContent = "Drag to select";
        });
    }

    if (btnConfirmRoi) {
        btnConfirmRoi.addEventListener('click', confirmRoi);
    }

    function closePreviewModal() {
        previewModal.classList.add('hidden');
    }

    async function loadPreview() {
        loadingPreview.classList.remove('hidden');
        try {
            const deviceType = document.querySelector('input[name="device"]:checked').value;
            // Add timestamp to prevent caching
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s timeout

            const res = await fetch(`/api/preview?device=${deviceType}&t=${Date.now()}`, {
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.error || "Failed to load preview");
            }
            
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            
            previewImage = new Image();
            previewImage.onload = () => {
                loadingPreview.classList.add('hidden');
                fitCanvasToImage();
                drawPreviewCanvas();
            };
            previewImage.src = url;

        } catch (e) {
            console.error(e);
            loadingPreview.classList.add('hidden');
            // Show more specific error if available from response logic
            if (e.name === 'AbortError') {
                alert("Preview timed out. Device might be busy or disconnected.");
            } else {
                alert("Could not load preview. " + (e.message || "Check connection."));
            }
        }
    }

    function fitCanvasToImage() {
        if (!previewImage) return;
        
        // Modal content area dimensions
        const container = previewModalContent;
        const maxWidth = container.clientWidth;
        const maxHeight = container.clientHeight;
        
        // Calculate aspect ratios
        const imgRatio = previewImage.width / previewImage.height;
        const containerRatio = maxWidth / maxHeight;
        
        let finalWidth, finalHeight;
        
        if (imgRatio > containerRatio) {
            // Image is wider than container
            finalWidth = maxWidth;
            finalHeight = maxWidth / imgRatio;
        } else {
            // Image is taller than container
            finalHeight = maxHeight;
            finalWidth = maxHeight * imgRatio;
        }
        
        previewCanvas.width = finalWidth;
        previewCanvas.height = finalHeight;
    }

    function drawPreviewCanvas() {
        if (!previewCanvas || !previewImage) return;
        const ctx = previewCanvas.getContext('2d');
        
        // Clear
        ctx.clearRect(0, 0, previewCanvas.width, previewCanvas.height);
        
        // Draw Image
        ctx.drawImage(previewImage, 0, 0, previewCanvas.width, previewCanvas.height);
        
        // Draw ROI Rect
        if (currentRect) {
            ctx.strokeStyle = '#22c55e'; // Green-500
            ctx.lineWidth = 2;
            ctx.strokeRect(currentRect.x, currentRect.y, currentRect.w, currentRect.h);
            
            ctx.fillStyle = 'rgba(34, 197, 94, 0.2)';
            ctx.fillRect(currentRect.x, currentRect.y, currentRect.w, currentRect.h);
        }
    }

    // Canvas Interaction
    previewCanvas.addEventListener('mousedown', (e) => {
        isDrawing = true;
        const rect = previewCanvas.getBoundingClientRect();
        startX = e.clientX - rect.left;
        startY = e.clientY - rect.top;
        currentRect = { x: startX, y: startY, w: 0, h: 0 };
    });

    previewCanvas.addEventListener('mousemove', (e) => {
        if (!isDrawing) return;
        const rect = previewCanvas.getBoundingClientRect();
        const currentX = e.clientX - rect.left;
        const currentY = e.clientY - rect.top;
        
        currentRect.w = currentX - startX;
        currentRect.h = currentY - startY;
        
        drawPreviewCanvas();
        
        // Update info text
        // We can estimate size if we knew PPI, but here just show pixels or %
        const pctW = Math.round((Math.abs(currentRect.w) / previewCanvas.width) * 100);
        const pctH = Math.round((Math.abs(currentRect.h) / previewCanvas.height) * 100);
        previewRoiInfo.textContent = `Selection: ${pctW}% x ${pctH}%`;
    });

    previewCanvas.addEventListener('mouseup', () => {
        isDrawing = false;
        // Normalize rect (handle negative width/height)
        if (currentRect) {
            if (currentRect.w < 0) {
                currentRect.x += currentRect.w;
                currentRect.w = Math.abs(currentRect.w);
            }
            if (currentRect.h < 0) {
                currentRect.y += currentRect.h;
                currentRect.h = Math.abs(currentRect.h);
            }
            
            // Ignore tiny clicks
            if (currentRect.w < 5 || currentRect.h < 5) {
                currentRect = null;
                drawPreviewCanvas();
            }
        }
    });

    function confirmRoi() {
        if (!currentRect || !previewCanvas.width) {
            roiSelection = null;
            roiValue.innerHTML = roiSlider.value + " x " + roiSlider.value + " cm"; // Reset text
            closePreviewModal();
            return;
        }
        
        // Calculate percentages
        roiSelection = {
            x: currentRect.x / previewCanvas.width,
            y: currentRect.y / previewCanvas.height,
            w: currentRect.w / previewCanvas.width,
            h: currentRect.h / previewCanvas.height
        };
        
        roiValue.innerHTML = `<span class="text-green-500">Custom ROI</span>`;
        closePreviewModal();
    }

    // ==========================================
    // Resizable Columns Logic
    // ==========================================
    const resizer1 = document.getElementById('resizer-1');
    const resizer2 = document.getElementById('resizer-2');
    const pane1 = document.getElementById('pane-history-list');
    const pane2 = document.getElementById('pane-maps-preview');

    function initResize(resizer, targetPane) {
        if (!resizer || !targetPane) return;

        let startX, startWidth;

        resizer.addEventListener('mousedown', (e) => {
            e.preventDefault();
            startX = e.clientX;
            startWidth = targetPane.getBoundingClientRect().width;
            
            document.body.style.cursor = 'col-resize';
            document.body.classList.add('select-none'); // Prevent text selection
            
            // Disable iframe pointer events if any (not here, but good practice)
            
            const onMouseMove = (e) => {
                const dx = e.clientX - startX;
                const newWidth = startWidth + dx;
                
                // Min/Max constraints
                if (newWidth > 150 && newWidth < window.innerWidth * 0.8) {
                    targetPane.style.width = `${newWidth}px`;
                    targetPane.style.flex = 'none'; // Disable flex sizing to enforce px width
                }
                
                // Resize 3D View
                onWindowResize();
            };
            
            const onMouseUp = () => {
                document.body.style.cursor = '';
                document.body.classList.remove('select-none');
                window.removeEventListener('mousemove', onMouseMove);
                window.removeEventListener('mouseup', onMouseUp);
            };
            
            window.addEventListener('mousemove', onMouseMove);
            window.addEventListener('mouseup', onMouseUp);
        });
    }

    initResize(resizer1, pane1);
    initResize(resizer2, pane2);

});
