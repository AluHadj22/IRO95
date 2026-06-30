/**
 * profile_check.js
 * Глобальные функции для проверки заполненности профиля пользователя
 * Используются на всех страницах для предупреждения пользователя
 */

// ============================================================
// ОСНОВНАЯ ФУНКЦИЯ ПРОВЕРКИ ПРОФИЛЯ
// ============================================================

/**
 * Проверяет, заполнен ли профиль текущего пользователя
 * @returns {Promise<Object|null>} Результат проверки или null при ошибке
 */
async function checkProfileComplete() {
    const token = localStorage.getItem('token');
    if (!token) return null;
    
    try {
        const response = await fetch('/api/profile/check-complete', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (response.ok) {
            return await response.json();
        }
        return null;
    } catch (error) {
        console.error('Error checking profile:', error);
        return null;
    }
}

// ============================================================
// ПОКАЗ ПРЕДУПРЕЖДЕНИЯ В НАВБАРЕ
// ============================================================

/**
 * Добавляет иконку-предупреждение в навбар, если профиль не заполнен
 */
function addProfileWarningToNavbar() {
    const navLinks = document.getElementById('navLinks');
    if (!navLinks) return;
    
    // Ищем ссылку на профиль
    const profileLink = navLinks.querySelector('a[href="/profile"]');
    if (!profileLink) return;
    
    // Проверяем, есть ли уже предупреждение
    if (profileLink.querySelector('.profile-warning-icon')) return;
    
    // Добавляем иконку предупреждения
    const warningIcon = document.createElement('span');
    warningIcon.className = 'profile-warning-icon';
    warningIcon.innerHTML = '<i class="bi bi-exclamation-triangle-fill text-warning me-1" style="font-size: 0.9rem;" title="Профиль не заполнен"></i>';
    profileLink.prepend(warningIcon);
}

/**
 * Убирает предупреждение из навбара
 */
function removeProfileWarningFromNavbar() {
    const warningIcons = document.querySelectorAll('.profile-warning-icon');
    warningIcons.forEach(icon => icon.remove());
}

// ============================================================
// ПОКАЗ TOAST-УВЕДОМЛЕНИЯ
// ============================================================

/**
 * Показывает toast-уведомление о необходимости заполнить профиль
 */
function showProfileWarningToast() {
    if (typeof showToast !== 'function') {
        console.warn('showToast function not available');
        return;
    }
    
    showToast(
        '⚠️ Для доступа к курсам заполните профиль в разделе "Мои данные"',
        'warning'
    );
}

// ============================================================
// СОЗДАНИЕ БАННЕРА НА СТРАНИЦЕ
// ============================================================

/**
 * Создает баннер-предупреждение на странице (для дашборда и других страниц)
 * @param {string} containerSelector - CSS-селектор контейнера для вставки баннера
 * @param {string} message - Сообщение для баннера
 */
function createProfileWarningBanner(containerSelector, message) {
    // Удаляем старый баннер, если есть
    const oldBanner = document.querySelector('.profile-warning-banner');
    if (oldBanner) oldBanner.remove();
    
    const container = document.querySelector(containerSelector);
    if (!container) return;
    
    const banner = document.createElement('div');
    banner.className = 'alert alert-warning profile-warning-banner';
    banner.style.cssText = `
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 12px;
        border-left: 4px solid #f59e0b;
    `;
    banner.innerHTML = `
        <div>
            <i class="bi bi-exclamation-triangle-fill me-2" style="color: #d97706;"></i>
            <strong style="color: #92400e;">Внимание!</strong>
            <span style="color: #92400e;">${message || 'Для доступа к курсам необходимо заполнить все обязательные поля профиля.'}</span>
        </div>
        <a href="/profile" class="btn btn-warning btn-sm" style="border-radius: 10px; font-weight: 600; white-space: nowrap;">
            <i class="bi bi-pencil-square me-1"></i>Заполнить профиль
        </a>
    `;
    
    container.parentNode.insertBefore(banner, container.nextSibling);
}

// ============================================================
// ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА ПРОВЕРКИ
// ============================================================

/**
 * Запускает проверку профиля и выполняет действия в зависимости от результата
 * @param {Object} options - Настройки
 * @param {boolean} options.showToast - Показывать ли toast-уведомление
 * @param {boolean} options.showBanner - Показывать ли баннер на странице
 * @param {string} options.bannerContainer - Селектор контейнера для баннера
 * @param {string} options.bannerMessage - Сообщение для баннера
 * @param {boolean} options.showNavbarWarning - Показывать ли предупреждение в навбаре
 */
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
        // Профиль не заполнен
        
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
        // Профиль заполнен или пользователь не авторизован
        
        if (showNavbarWarning) {
            removeProfileWarningFromNavbar();
        }
        
        return true;
    }
}

// ============================================================
// АВТОМАТИЧЕСКИЙ ЗАПУСК ПРИ ЗАГРУЗКЕ СТРАНИЦЫ
// ============================================================

// Проверяем профиль при загрузке страницы, если пользователь авторизован
document.addEventListener('DOMContentLoaded', function() {
    const token = localStorage.getItem('token');
    if (token) {
        // Запускаем проверку с настройками по умолчанию
        // На страницах, где нужен баннер, можно переопределить через data-атрибуты
        const showBanner = document.body.dataset.profileBanner === 'true';
        const bannerContainer = document.body.dataset.profileBannerContainer || '.dashboard-stats';
        const bannerMessage = document.body.dataset.profileBannerMessage || 
            'Для доступа к курсам необходимо заполнить все обязательные поля профиля.';
        
        runProfileCheck({
            showToast: true,
            showBanner: showBanner,
            bannerContainer: bannerContainer,
            bannerMessage: bannerMessage,
            showNavbarWarning: true
        });
    }
});

// ============================================================
// ЭКСПОРТ ФУНКЦИЙ ДЛЯ ИСПОЛЬЗОВАНИЯ В ДРУГИХ СКРИПТАХ
// ============================================================

// Делаем функции глобальными для использования в других скриптах
window.checkProfileComplete = checkProfileComplete;
window.addProfileWarningToNavbar = addProfileWarningToNavbar;
window.removeProfileWarningFromNavbar = removeProfileWarningFromNavbar;
window.showProfileWarningToast = showProfileWarningToast;
window.createProfileWarningBanner = createProfileWarningBanner;
window.runProfileCheck = runProfileCheck;