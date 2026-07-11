/**
 * profile_check.js
 * Глобальные функции для проверки заполненности профиля пользователя
 */

const PROFILE_CHECK_CONFIG = {
    toastDuration: 3000,
    bannerSelectors: ['.dashboard-stats', '.container > .row:first-child', 'main > .container'],
    debounceDelay: 300
};

let profileCheckCache = null;
let profileCheckCacheTime = 0;
const CACHE_TTL = 30000;

async function checkProfileComplete() {
    const token = localStorage.getItem('token');
    if (!token) return null;
    
    const now = Date.now();
    if (profileCheckCache && (now - profileCheckCacheTime) < CACHE_TTL) {
        return profileCheckCache;
    }
    
    try {
        const response = await fetch('/api/profile/check-complete', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (response.ok) {
            profileCheckCache = await response.json();
            profileCheckCacheTime = now;
            return profileCheckCache;
        }
        return null;
    } catch (error) {
        console.error('Error checking profile:', error);
        return null;
    }
}

function addProfileWarningToNavbar() {
    const navLinks = document.getElementById('navLinks');
    if (!navLinks) return;
    
    const profileLink = navLinks.querySelector('a[href="/profile"]');
    if (!profileLink) return;
    
    if (profileLink.querySelector('.profile-warning-icon')) return;
    
    const warningIcon = document.createElement('span');
    warningIcon.className = 'profile-warning-icon';
    warningIcon.innerHTML = '<i class="bi bi-exclamation-triangle-fill text-warning me-1" style="font-size:0.9rem;" title="Профиль не заполнен"></i>';
    profileLink.prepend(warningIcon);
}

function removeProfileWarningFromNavbar() {
    document.querySelectorAll('.profile-warning-icon').forEach(icon => icon.remove());
}

function showProfileWarningToast() {
    if (typeof showToast !== 'function') {
        console.warn('showToast function not available');
        return;
    }
    showToast('⚠️ Для доступа к курсам заполните профиль в разделе "Мои данные"', 'warning');
}

function createProfileWarningBanner(containerSelector, message) {
    const oldBanner = document.querySelector('.profile-warning-banner');
    if (oldBanner) oldBanner.remove();
    
    let container = document.querySelector(containerSelector);
    if (!container) {
        for (const selector of PROFILE_CHECK_CONFIG.bannerSelectors) {
            const el = document.querySelector(selector);
            if (el) {
                container = el;
                break;
            }
        }
    }
    if (!container) return;
    
    const banner = document.createElement('div');
    banner.className = 'alert alert-warning profile-warning-banner';
    Object.assign(banner.style, {
        borderRadius: '12px',
        padding: '16px 20px',
        marginBottom: '20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px',
        borderLeft: '4px solid #f59e0b'
    });
    banner.innerHTML = `
        <div>
            <i class="bi bi-exclamation-triangle-fill me-2" style="color:#d97706;"></i>
            <strong style="color:#92400e;">Внимание!</strong>
            <span style="color:#92400e;">${message || 'Для доступа к курсам необходимо заполнить все обязательные поля профиля.'}</span>
        </div>
        <a href="/profile" class="btn btn-warning btn-sm" style="border-radius:10px;font-weight:600;white-space:nowrap;">
            <i class="bi bi-pencil-square me-1"></i>Заполнить профиль
        </a>
    `;
    
    container.parentNode.insertBefore(banner, container.nextSibling);
}

async function runProfileCheck(options = {}) {
    const {
        showToast = true,
        showBanner = false,
        bannerContainer = '.dashboard-stats',
        bannerMessage = 'Для доступа к курсам необходимо заполнить все обязательные поля профиля.',
        showNavbarWarning = true
    } = options;
    
    const result = await checkProfileComplete();
    
    if (result && !result.is_complete) {
        if (showNavbarWarning) {
            addProfileWarningToNavbar();
        }
        if (showToast) {
            showProfileWarningToast();
        }
        if (showBanner) {
            createProfileWarningBanner(bannerContainer, bannerMessage);
        }
        return false;
    } else {
        if (showNavbarWarning) {
            removeProfileWarningFromNavbar();
        }
        return true;
    }
}

let profileCheckRunning = false;
let profileCheckTimeout = null;

function scheduleProfileCheck(options = {}, delay = 500) {
    if (profileCheckTimeout) {
        clearTimeout(profileCheckTimeout);
    }
    profileCheckTimeout = setTimeout(() => {
        profileCheckTimeout = null;
        if (!profileCheckRunning) {
            profileCheckRunning = true;
            runProfileCheck(options).finally(() => {
                profileCheckRunning = false;
            });
        }
    }, delay);
}

document.addEventListener('DOMContentLoaded', function() {
    const token = localStorage.getItem('token');
    if (!token) return;
    
    const showBanner = document.body.dataset.profileBanner === 'true';
    const bannerContainer = document.body.dataset.profileBannerContainer || '.dashboard-stats';
    const bannerMessage = document.body.dataset.profileBannerMessage || 
        'Для доступа к курсам необходимо заполнить все обязательные поля профиля.';
    
    scheduleProfileCheck({
        showToast: true,
        showBanner: showBanner,
        bannerContainer: bannerContainer,
        bannerMessage: bannerMessage,
        showNavbarWarning: true
    }, 300);
});

document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') {
        const token = localStorage.getItem('token');
        if (token) {
            profileCheckCache = null;
            profileCheckCacheTime = 0;
            scheduleProfileCheck({ showToast: false, showNavbarWarning: true }, 200);
        }
    }
});

window.checkProfileComplete = checkProfileComplete;
window.addProfileWarningToNavbar = addProfileWarningToNavbar;
window.removeProfileWarningFromNavbar = removeProfileWarningFromNavbar;
window.showProfileWarningToast = showProfileWarningToast;
window.createProfileWarningBanner = createProfileWarningBanner;
window.runProfileCheck = runProfileCheck;
window.scheduleProfileCheck = scheduleProfileCheck;