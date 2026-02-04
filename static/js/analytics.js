let analyticsCharts = {
    registrationsChart: null,
    revenueChart: null,
    purchasesChart: null,
    subscriptionsChart: null
};


function formatDate(dateStr) {
    const d = new Date(dateStr);
    return isNaN(d) ? dateStr : d.toLocaleDateString('ru-RU');
}

function formatNumber(num) {
    return Number(num).toLocaleString('ru-RU');
}

function destroyChart(chartKey) {
    if (analyticsCharts[chartKey]) {
        analyticsCharts[chartKey].destroy();
        analyticsCharts[chartKey] = null;
    }
}

function showNoDataMessage(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const container = canvas.closest('.chart-container');
    if (!container) return;

    if (!container.querySelector('.no-data-message')) {
        const div = document.createElement('div');
        div.className = 'no-data-message';
        div.textContent = 'Нет данных для отображения';
        container.appendChild(div);
    }
}


function createChart(canvasId, config, chartKey) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    destroyChart(chartKey);
    const ctx = canvas.getContext('2d');
    analyticsCharts[chartKey] = new Chart(ctx, config);
}


function initRegistrationsChart(data) {
    if (!data.registrations?.length) {
        showNoDataMessage('registrationsChart');
        return;
    }

    createChart('registrationsChart', {
        type: 'line',
        data: {
            labels: data.registrations.map(r => formatDate(r.date)),
            datasets: [{
                label: 'Регистрации',
                data: data.registrations.map(r => r.count),
                borderWidth: 2,
                tension: 0.4,
                fill: true
            }]
        },
        options: { responsive: true }
    }, 'registrationsChart');
}


function initRevenueChart(data) {
    if (!data.daily_revenue?.length) {
        showNoDataMessage('revenueChart');
        return;
    }

    createChart('revenueChart', {
        type: 'bar',
        data: {
            labels: data.daily_revenue.map(r => formatDate(r.date)),
            datasets: [{
                label: 'Выручка ₽',
                data: data.daily_revenue.map(r => r.revenue)
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    ticks: {
                        callback: v => formatNumber(v) + ' ₽'
                    }
                }
            }
        }
    }, 'revenueChart');
}


function initPurchasesChart(data) {
    if (!data.purchases?.length) {
        showNoDataMessage('purchasesChart');
        return;
    }

    createChart('purchasesChart', {
        type: 'bar',
        data: {
            labels: data.purchases.map(p => formatDate(p.date)),
            datasets: [{
                label: 'Покупки',
                data: data.purchases.map(p => p.count)
            }]
        },
        options: { responsive: true }
    }, 'purchasesChart');
}


function initSubscriptionsChart(data) {
    if (!data.subscriptions?.length) {
        showNoDataMessage('subscriptionsChart');
        return;
    }

    const labels = data.subscriptions.map(s => s.plan);
    const sold = data.subscriptions.map(s => s.sold);
    const revenue = data.subscriptions.map(s => s.revenue);

    createChart('subscriptionsChart', {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Продано подписок',
                    data: sold,
                    yAxisID: 'y'
                },
                {
                    label: 'Выручка ₽',
                    data: revenue,
                    type: 'line',
                    yAxisID: 'y1',
                    tension: 0.4,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Количество' },
                    ticks: { callback: v => formatNumber(v) }
                },
                y1: {
                    beginAtZero: true,
                    position: 'right',
                    title: { display: true, text: 'Выручка ₽' },
                    grid: { drawOnChartArea: false },
                    ticks: { callback: v => formatNumber(v) + ' ₽' }
                }
            }
        }
    }, 'subscriptionsChart');
}


function initAnalyticsCharts() {
    if (typeof Chart === 'undefined') {
        console.error('Chart.js not loaded');
        return;
    }

    let data = window.analyticsChartData;

    if (!data) {
        const el = document.getElementById('analytics-data');
        if (el) {
            try {
                data = JSON.parse(el.textContent);
                window.analyticsChartData = data;
            } catch (e) {
                console.error('Invalid analytics JSON');
                return;
            }
        }
    }

    if (!data) return;

    initRegistrationsChart(data);
    initRevenueChart(data);
    initPurchasesChart(data);
    initSubscriptionsChart(data);
}


if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAnalyticsCharts);
} else {
    initAnalyticsCharts();
}
