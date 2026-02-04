function confirmCancelSubscription(planName, daysSinceStart) {
    let message = `Вы уверены, что хотите отменить подписку "${planName}"?`;
    
    if (daysSinceStart > 14) {
        message += '\n\nВнимание: прошло более 14 дней с начала подписки. ' +
                  'Возврат средств возможен только в течение 14 дней.';
    }
    
    return confirm(message);
}

document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        if (alert.classList.contains('alert-info')) {
            return;
        }
        
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.parentNode.removeChild(alert);
                }
            }, 500);
        }, 5000);
    });
    
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(btn => {
        btn.addEventListener('mouseenter', () => {
            btn.style.transform = 'translateY(-2px)';
        });
        btn.addEventListener('mouseleave', () => {
            btn.style.transform = 'translateY(0)';
        });
    });
    
    const infoAlerts = document.querySelectorAll('.alert-info');
    infoAlerts.forEach(alert => {
        if (!alert.querySelector('.close-alert-btn')) {
            const closeBtn = document.createElement('button');
            closeBtn.type = 'button';
            closeBtn.className = 'close-alert-btn';
            closeBtn.innerHTML = '&times;';
            closeBtn.style.cssText = `
                position: absolute;
                top: 5px;
                right: 10px;
                background: none;
                border: none;
                font-size: 20px;
                cursor: pointer;
                color: #666;
            `;
            closeBtn.addEventListener('click', () => {
                alert.style.opacity = '0';
                setTimeout(() => {
                    if (alert.parentNode) {
                        alert.parentNode.removeChild(alert);
                    }
                }, 500);
            });
            alert.style.position = 'relative';
            alert.appendChild(closeBtn);
        }
    });
});