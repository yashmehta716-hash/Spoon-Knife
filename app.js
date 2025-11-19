// F&O IV Spike Tracing Application
// Main application state
let appState = {
    monitoring: false,
    monitorInterval: null,
    currentSymbol: 'NIFTY',
    currentExpiry: 'current',
    spikeThreshold: 20,
    optionsData: [],
    historicalIV: [],
    alerts: [],
    chart: null
};

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

function initializeApp() {
    // Set up event listeners
    document.getElementById('symbol').addEventListener('change', handleSymbolChange);
    document.getElementById('expiry').addEventListener('change', handleExpiryChange);
    document.getElementById('spikeThreshold').addEventListener('change', handleThresholdChange);
    document.getElementById('refreshBtn').addEventListener('click', refreshData);
    document.getElementById('toggleMonitor').addEventListener('click', toggleMonitoring);
    document.getElementById('filterSpikes').addEventListener('change', filterSpikes);
    document.getElementById('sortBy').addEventListener('change', sortOptionsChain);

    // Initialize chart
    initializeChart();

    // Load initial data
    refreshData();
}

function handleSymbolChange(e) {
    appState.currentSymbol = e.target.value;
    refreshData();
}

function handleExpiryChange(e) {
    appState.currentExpiry = e.target.value;
    refreshData();
}

function handleThresholdChange(e) {
    appState.spikeThreshold = parseInt(e.target.value);
}

function toggleMonitoring() {
    const btn = document.getElementById('toggleMonitor');
    const status = document.getElementById('monitorStatus');

    if (appState.monitoring) {
        // Stop monitoring
        clearInterval(appState.monitorInterval);
        appState.monitoring = false;
        btn.textContent = 'Start Monitor';
        btn.classList.remove('active');
        status.textContent = 'Idle';
        status.classList.remove('active');
    } else {
        // Start monitoring
        appState.monitoring = true;
        btn.textContent = 'Stop Monitor';
        btn.classList.add('active');
        status.textContent = 'Active';
        status.classList.add('active');

        // Refresh every 5 seconds
        appState.monitorInterval = setInterval(refreshData, 5000);
    }
}

function refreshData() {
    // Generate mock options chain data with IV
    generateOptionsData();

    // Update the UI
    updateOptionsChain();
    updateStats();
    updateChart();
    detectSpikes();
    updateLastUpdateTime();
}

function generateOptionsData() {
    const symbol = appState.currentSymbol;
    const basePrice = getBasePrice(symbol);
    const strikes = generateStrikes(basePrice);

    appState.optionsData = strikes.map(strike => {
        const callData = generateOptionData(strike, basePrice, 'CE');
        const putData = generateOptionData(strike, basePrice, 'PE');

        return {
            strike: strike,
            call: callData,
            put: putData
        };
    });
}

function getBasePrice(symbol) {
    const prices = {
        'NIFTY': 19500,
        'BANKNIFTY': 44000,
        'FINNIFTY': 19800,
        'RELIANCE': 2450,
        'TCS': 3600,
        'INFY': 1450
    };
    return prices[symbol] || 19500;
}

function generateStrikes(basePrice) {
    const strikes = [];
    const interval = basePrice > 10000 ? 100 : 50;
    const range = 10;

    for (let i = -range; i <= range; i++) {
        strikes.push(Math.round((basePrice + (i * interval)) / interval) * interval);
    }

    return strikes;
}

function generateOptionData(strike, spotPrice, type) {
    const isITM = (type === 'CE' && strike < spotPrice) || (type === 'PE' && strike > spotPrice);
    const isATM = Math.abs(strike - spotPrice) < 100;

    // Base IV with random variation
    let baseIV = isATM ? 18 + Math.random() * 8 :
                 isITM ? 15 + Math.random() * 5 :
                 12 + Math.random() * 10;

    // Sometimes create spikes for demonstration
    const spikeChance = Math.random();
    let ivChange = (Math.random() - 0.5) * 10;

    if (spikeChance > 0.95) {
        // High spike
        ivChange = 20 + Math.random() * 30;
    } else if (spikeChance > 0.9) {
        // Medium spike
        ivChange = 10 + Math.random() * 15;
    }

    const currentIV = baseIV + (ivChange / 100) * baseIV;

    // Calculate option price based on IV and moneyness
    const intrinsicValue = type === 'CE' ? Math.max(0, spotPrice - strike) : Math.max(0, strike - spotPrice);
    const timeValue = (currentIV / 100) * Math.sqrt(30/365) * strike * 0.4;
    const ltp = intrinsicValue + timeValue;

    return {
        iv: currentIV,
        ivChange: ivChange,
        previousIV: baseIV,
        ltp: ltp.toFixed(2),
        volume: Math.floor(Math.random() * 100000),
        oi: Math.floor(Math.random() * 500000),
        type: type
    };
}

function updateOptionsChain() {
    const tbody = document.getElementById('chainBody');
    tbody.innerHTML = '';

    const threshold = appState.spikeThreshold;
    const filterSpikesOnly = document.getElementById('filterSpikes').checked;

    appState.optionsData.forEach(row => {
        const callSpike = Math.abs(row.call.ivChange) >= threshold;
        const putSpike = Math.abs(row.put.ivChange) >= threshold;

        if (filterSpikesOnly && !callSpike && !putSpike) {
            return;
        }

        const tr = document.createElement('tr');

        // Call side
        tr.innerHTML = `
            <td class="call-side ${callSpike ? 'iv-spike' : ''}">${row.call.iv.toFixed(2)}%</td>
            <td class="call-side ${row.call.ivChange >= 0 ? 'positive-change' : 'negative-change'}">
                ${row.call.ivChange >= 0 ? '+' : ''}${row.call.ivChange.toFixed(2)}%
            </td>
            <td class="call-side">${formatNumber(row.call.oi)}</td>
            <td class="call-side">${formatNumber(row.call.volume)}</td>
            <td class="call-side">₹${row.call.ltp}</td>
            <td class="strike-cell">${row.strike}</td>
            <td class="put-side">₹${row.put.ltp}</td>
            <td class="put-side">${formatNumber(row.put.volume)}</td>
            <td class="put-side">${formatNumber(row.put.oi)}</td>
            <td class="put-side ${row.put.ivChange >= 0 ? 'positive-change' : 'negative-change'}">
                ${row.put.ivChange >= 0 ? '+' : ''}${row.put.ivChange.toFixed(2)}%
            </td>
            <td class="put-side ${putSpike ? 'iv-spike' : ''}">${row.put.iv.toFixed(2)}%</td>
        `;

        tbody.appendChild(tr);
    });
}

function updateStats() {
    // Calculate statistics
    const callIVs = appState.optionsData.map(row => row.call.iv);
    const putIVs = appState.optionsData.map(row => row.put.iv);
    const allChanges = [
        ...appState.optionsData.map(row => Math.abs(row.call.ivChange)),
        ...appState.optionsData.map(row => Math.abs(row.put.ivChange))
    ];

    const avgCallIV = (callIVs.reduce((a, b) => a + b, 0) / callIVs.length).toFixed(2);
    const avgPutIV = (putIVs.reduce((a, b) => a + b, 0) / putIVs.length).toFixed(2);
    const maxChange = Math.max(...allChanges).toFixed(2);

    const spikes = appState.optionsData.reduce((count, row) => {
        if (Math.abs(row.call.ivChange) >= appState.spikeThreshold) count++;
        if (Math.abs(row.put.ivChange) >= appState.spikeThreshold) count++;
        return count;
    }, 0);

    // Update UI
    document.getElementById('activeSpikes').textContent = spikes;
    document.getElementById('avgIVCall').textContent = avgCallIV + '%';
    document.getElementById('avgIVPut').textContent = avgPutIV + '%';
    document.getElementById('maxIVChange').textContent = '+' + maxChange + '%';
}

function detectSpikes() {
    const threshold = appState.spikeThreshold;
    const newAlerts = [];

    appState.optionsData.forEach(row => {
        // Check call side
        if (Math.abs(row.call.ivChange) >= threshold) {
            newAlerts.push({
                symbol: appState.currentSymbol,
                strike: row.strike,
                type: 'CE',
                iv: row.call.iv,
                change: row.call.ivChange,
                severity: Math.abs(row.call.ivChange) >= threshold * 1.5 ? 'high' : 'medium',
                time: new Date()
            });
        }

        // Check put side
        if (Math.abs(row.put.ivChange) >= threshold) {
            newAlerts.push({
                symbol: appState.currentSymbol,
                strike: row.strike,
                type: 'PE',
                iv: row.put.iv,
                change: row.put.ivChange,
                severity: Math.abs(row.put.ivChange) >= threshold * 1.5 ? 'high' : 'medium',
                time: new Date()
            });
        }
    });

    // Add new alerts to beginning of array
    appState.alerts = [...newAlerts, ...appState.alerts].slice(0, 50); // Keep only last 50 alerts

    updateAlerts();
}

function updateAlerts() {
    const container = document.getElementById('alertsContainer');

    if (appState.alerts.length === 0) {
        container.innerHTML = '<p class="no-alerts">No spikes detected. Monitoring...</p>';
        return;
    }

    container.innerHTML = appState.alerts.slice(0, 10).map(alert => `
        <div class="alert-item spike-${alert.severity}">
            <div class="alert-header">
                <span class="alert-symbol">${alert.symbol} ${alert.strike} ${alert.type}</span>
                <span class="alert-time">${formatTime(alert.time)}</span>
            </div>
            <div class="alert-details">
                IV: <span class="spike-value">${alert.iv.toFixed(2)}%</span>
                (${alert.change >= 0 ? '+' : ''}${alert.change.toFixed(2)}% change)
            </div>
        </div>
    `).join('');
}

function initializeChart() {
    const ctx = document.getElementById('ivChart').getContext('2d');

    appState.chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'ATM Call IV',
                    data: [],
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.1)',
                    tension: 0.4
                },
                {
                    label: 'ATM Put IV',
                    data: [],
                    borderColor: 'rgb(255, 99, 132)',
                    backgroundColor: 'rgba(255, 99, 132, 0.1)',
                    tension: 0.4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                title: {
                    display: true,
                    text: 'ATM Options IV Trend'
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: 'Implied Volatility (%)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Time'
                    }
                }
            }
        }
    });
}

function updateChart() {
    // Find ATM options
    const basePrice = getBasePrice(appState.currentSymbol);
    const atmRow = appState.optionsData.reduce((closest, row) => {
        return Math.abs(row.strike - basePrice) < Math.abs(closest.strike - basePrice) ? row : closest;
    });

    const timestamp = new Date().toLocaleTimeString();

    // Add new data point
    appState.chart.data.labels.push(timestamp);
    appState.chart.data.datasets[0].data.push(atmRow.call.iv);
    appState.chart.data.datasets[1].data.push(atmRow.put.iv);

    // Keep only last 20 data points
    if (appState.chart.data.labels.length > 20) {
        appState.chart.data.labels.shift();
        appState.chart.data.datasets[0].data.shift();
        appState.chart.data.datasets[1].data.shift();
    }

    appState.chart.update('none');
}

function filterSpikes() {
    updateOptionsChain();
}

function sortOptionsChain() {
    const sortBy = document.getElementById('sortBy').value;

    switch(sortBy) {
        case 'strike':
            appState.optionsData.sort((a, b) => a.strike - b.strike);
            break;
        case 'callIV':
            appState.optionsData.sort((a, b) => b.call.iv - a.call.iv);
            break;
        case 'putIV':
            appState.optionsData.sort((a, b) => b.put.iv - a.put.iv);
            break;
        case 'callChange':
            appState.optionsData.sort((a, b) => Math.abs(b.call.ivChange) - Math.abs(a.call.ivChange));
            break;
        case 'putChange':
            appState.optionsData.sort((a, b) => Math.abs(b.put.ivChange) - Math.abs(a.put.ivChange));
            break;
    }

    updateOptionsChain();
}

function updateLastUpdateTime() {
    const now = new Date();
    document.getElementById('lastUpdate').textContent = now.toLocaleTimeString();
}

function formatNumber(num) {
    if (num >= 10000000) return (num / 10000000).toFixed(2) + 'Cr';
    if (num >= 100000) return (num / 100000).toFixed(2) + 'L';
    if (num >= 1000) return (num / 1000).toFixed(2) + 'K';
    return num.toString();
}

function formatTime(date) {
    return date.toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// Add keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Space to toggle monitoring
    if (e.code === 'Space' && e.target.tagName !== 'INPUT') {
        e.preventDefault();
        toggleMonitoring();
    }
    // R to refresh
    if (e.code === 'KeyR' && e.ctrlKey) {
        e.preventDefault();
        refreshData();
    }
});
