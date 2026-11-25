// App state
let currentVideoData = null;
let currentTaskId = null;
let progressInterval = null;
let eventSource = null;
let saveStatusCheck = null;

// DOM elements
const videoUrlInput = document.getElementById('videoUrl');
const analyzeBtn = document.getElementById('analyzeBtn');
const resultsSection = document.getElementById('results');
const progressSection = document.getElementById('progress');
const formatsList = document.getElementById('formatsList');
const videoTitle = document.getElementById('videoTitle');
const videoAuthor = document.getElementById('videoAuthor');
const videoDuration = document.getElementById('videoDuration');
const videoThumbnail = document.getElementById('videoThumbnail');
const downloadPercent = document.getElementById('downloadPercent');
const videoWorkspace = document.getElementById('videoWorkspace');
const inspectorTitle = document.getElementById('inspectorTitle');
const progressText = document.getElementById('progressText');
const statusText = document.getElementById('statusText');
const speedText = document.getElementById('speedText');
const etaText = document.getElementById('etaText');
const cancelBtn = document.getElementById('cancelBtn');

// YouTube search elements
const ytSearchQuery = document.getElementById('ytSearchQuery');
const searchBtn = document.getElementById('searchBtn');
const clearSearchBtn = document.getElementById('clearSearch');
const ytSearchResults = document.getElementById('ytSearchResults');
let lastSearch = { query: '', items: [] };

// Tabs
const tabButtons = document.querySelectorAll('.tab-btn');
const searchTab = document.getElementById('searchTab');
const analyzeTab = document.getElementById('analyzeTab');

// Navigation elements
const navToggle = document.getElementById('navToggle');
const navMenu = document.getElementById('navMenu');


// Download ready elements  
const downloadReadyContainer = document.getElementById('downloadReadyContainer');
const downloadReadyBtn = document.getElementById('downloadReadyBtn');
const backToFormats = document.getElementById('backToFormats');

// Clear input elements
const clearInputBtn = document.getElementById('clearInput');

// Event listeners
document.addEventListener('DOMContentLoaded', function() {

    setActiveNavigation();
    restoreActiveDownload();

    analyzeTab.addEventListener('submit', event => {
        event.preventDefault();
        handleAnalyzeVideo();
    });
    searchTab.addEventListener('submit', event => {
        event.preventDefault();
        handleYoutubeSearch();
    });

    // Navigation functionality
    if (navToggle && navMenu) {
        navToggle.addEventListener('click', toggleMobileMenu);
        
        // Close menu when clicking on nav links
        const navLinks = navMenu.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', closeMobileMenu);
        });
        
        // Close menu when clicking outside
        document.addEventListener('click', function(e) {
            if (!navToggle.contains(e.target) && !navMenu.contains(e.target)) {
                closeMobileMenu();
            }
        });
    }
    // Tabs
    if (tabButtons && tabButtons.length) {
        tabButtons.forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.tab));
        });
    }
    if (clearSearchBtn && ytSearchQuery) {
        clearSearchBtn.addEventListener('click', () => {
            ytSearchQuery.value = '';
            lastSearch = { query: '', items: [] };
            ytSearchQuery.focus();
            if (ytSearchResults) ytSearchResults.innerHTML = '';
        });
    }
    
    // Auto-focus на поле ввода и восстановление последней ссылки
    if (videoUrlInput) {
        const lastUrl = localStorage.getItem('lastVideoUrl');
        if (lastUrl) {
            videoUrlInput.value = lastUrl;
        }
    }
    
    backToFormats.addEventListener('click', returnToFormats);
    downloadReadyBtn.addEventListener('click', event => {
        if (!currentTaskId || saveStatusCheck) {
            event.preventDefault();
            return;
        }
        saveStatusCheck = currentTaskId;
        downloadReadyBtn.setAttribute('aria-disabled', 'true');
        downloadReadyBtn.setAttribute('tabindex', '-1');
        downloadReadyBtn.textContent = 'Передаём файл…';
        backToFormats.disabled = true;
        statusText.textContent = 'Передаём файл в браузер';
        checkFileDelivery(currentTaskId);
    });

    // Кнопка отмены
    if (cancelBtn) {
        cancelBtn.addEventListener('click', cancelCurrentTask);
    }
    
    // Обработчик кнопки очистки поля
    if (clearInputBtn) {
        clearInputBtn.addEventListener('click', () => {
            if (videoUrlInput) {
                videoUrlInput.value = '';
                videoUrlInput.focus();
                localStorage.removeItem('lastVideoUrl');
            }
        });
    }
    
    // Показывать/скрывать кнопку очистки
    if (videoUrlInput && clearInputBtn) {
        const toggleClearButton = () => {
            if (videoUrlInput.value.trim()) {
                clearInputBtn.style.opacity = '1';
                clearInputBtn.style.visibility = 'visible';
            } else {
                clearInputBtn.style.opacity = '0';
                clearInputBtn.style.visibility = 'hidden';
            }
        };
        
        videoUrlInput.addEventListener('input', toggleClearButton);
        videoUrlInput.addEventListener('focus', toggleClearButton);
        videoUrlInput.addEventListener('blur', () => {
            setTimeout(toggleClearButton, 100); // Задержка для клика по кнопке
        });
        
        // Первоначальная проверка
        toggleClearButton();
    }
});

// Utility functions
function showFeedback(message, error = false) {
    const feedback = document.getElementById('signal-feedback');
    const notice = document.createElement('p');
    notice.className = error ? 'error-message' : 'success-message';
    if (!message) {
        feedback.replaceChildren();
        return;
    }
    notice.textContent = message;
    if (error) notice.setAttribute('role', 'alert');
    feedback.replaceChildren(notice);
}

function showError(message) {
    showFeedback(message, true);
}

function showSuccess(message) {
    showFeedback(message);
}

function switchTab(tab) {
    ytSearchResults.hidden = tab !== 'search';
    tabButtons.forEach(button => {
        const active = button.dataset.tab === tab;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', String(active));
    });
    if (tab === 'search') {
        if (searchTab) searchTab.style.display = 'block';
        if (analyzeTab) analyzeTab.style.display = 'none';
        // восстановим результаты последнего поиска, если пусто
        if (ytSearchResults && ytSearchResults.children.length === 0 && lastSearch.items.length) {
            renderYoutubeSearchResults(lastSearch.items);
        }
    } else {
        if (searchTab) searchTab.style.display = 'none';
        if (analyzeTab) analyzeTab.style.display = 'block';
    }
}

function validateUrl(url) {
    if (!url.trim()) {
        return 'Пожалуйста, введите ссылку на видео';
    }
    
    try {
        const address = new URL(url);
        const supported = /(^|\.)(youtube\.com|youtu\.be|instagram\.com|vk\.com|vkvideo\.ru)$/i;
        if (!['http:', 'https:'].includes(address.protocol) || !supported.test(address.hostname)) {
            return 'Вставьте ссылку на видео с YouTube, Instagram или VK.';
        }
    } catch {
        return 'Проверьте адрес ссылки.';
    }

    return null;
}

function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return 'Неизвестно';
    
    const sizes = ['Б', 'КБ', 'МБ', 'ГБ'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
}

function formatDuration(seconds) {
    if (!seconds) return '';
    
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    
    if (minutes >= 60) {
        const hours = Math.floor(minutes / 60);
        const remainingMinutes = minutes % 60;
        return `${hours}:${remainingMinutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
    }
    
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

function setButtonLoading(button, isLoading) {
    button.disabled = isLoading;
    button.setAttribute('aria-busy', String(isLoading));
    const status = document.getElementById('request-status');
    if (isLoading) {
        status.dataset.request = button.id;
        status.textContent = button === analyzeBtn ? 'Получаем форматы видео' : 'Ищем ролики на YouTube';
    } else if (status.dataset.request === button.id) {
        status.textContent = '';
    }
}

// Main functions
async function handleAnalyzeVideo() {
    if (!videoUrlInput || analyzeBtn.disabled) return;
    if (!progressSection.hidden && downloadReadyContainer.hidden) {
        showSuccess('Дождитесь завершения или отмените текущую загрузку.');
        cancelBtn.focus();
        return;
    }
    
    const url = videoUrlInput.value.trim();
    
    // Валидация
    const validationError = validateUrl(url);
    if (validationError) {
        showError(validationError);
        return;
    }
    
    // Сохраняем ссылку в localStorage
    localStorage.setItem('lastVideoUrl', url);
    
    // Показываем загрузку
    showSuccess('');
    setButtonLoading(analyzeBtn, true);
    hideResults();

    try {
        const response = await fetch('/api/get-formats', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url: url })
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Ошибка ${response.status}: ${response.statusText}`);
        }
        
        const videoData = await response.json();
        currentVideoData = videoData;
        
        displayVideoInfo(videoData);
        displayFormats(videoData.formats.filter(format => format.video_format_id));
        showResults();
        
        showSuccess('');
        videoTitle.focus();
        
    } catch (error) {
        console.error('Error analyzing video:', error);
        showError(`Ошибка при анализе видео: ${error.message}`);
    } finally {
        setButtonLoading(analyzeBtn, false);
    }
}

async function handleYoutubeSearch() {
    const q = ytSearchQuery ? ytSearchQuery.value.trim() : '';
    if (!q) {
        showError('Введите поисковый запрос');
        return;
    }
    if (searchBtn.disabled) return;
    showSuccess('');
    setButtonLoading(searchBtn, true);
    if (ytSearchResults) ytSearchResults.innerHTML = '';
    try {
        const resp = await fetch(`/api/youtube/search?q=${encodeURIComponent(q)}`);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Не удалось выполнить поиск');
        }
        const data = await resp.json();
        lastSearch = { query: q, items: Array.isArray(data.items) ? data.items : [] };
        renderYoutubeSearchResults(lastSearch.items);
    } catch (e) {
        showError(e.message);
    } finally {
        setButtonLoading(searchBtn, false);
    }
}

function renderYoutubeSearchResults(items) {
    if (!ytSearchResults) return;
    if (!items || items.length === 0) {
        ytSearchResults.innerHTML = '<p>Ничего не найдено</p>';
        return;
    }
    ytSearchResults.innerHTML = '';
    items.slice(0, 6).forEach(item => {
        const div = document.createElement('div');
        div.className = 'format-item yt-result';
        if (item.thumbnail_url) div.append(mediaThumbnail(item.thumbnail_url, 'yt-thumb'));
        const title = document.createElement('strong');
        title.className = 'yt-title';
        title.textContent = item.title || 'Без названия';
        const meta = document.createElement('span');
        meta.textContent = [item.author, item.duration && formatDuration(item.duration)].filter(Boolean).join(' · ');
        const open = document.createElement('button');
        open.textContent = 'Открыть';
        open.addEventListener('click', () => {
            switchTab('analyze');
            videoUrlInput.value = item.video_url;
            handleAnalyzeVideo();
        });
        meta.className = 'yt-meta';
        div.append(title, meta, open);
        ytSearchResults.appendChild(div);
    });
}

function displayVideoInfo(videoData) {
    if (videoTitle) videoTitle.textContent = videoData.title || 'Без названия';
    if (videoAuthor) videoAuthor.textContent = videoData.author ? `Автор: ${videoData.author}` : '';
    if (videoDuration) videoDuration.textContent = videoData.duration ? `Длительность: ${formatDuration(videoData.duration)}` : '';
    
    if (videoThumbnail && videoData.preview_url) {
        videoThumbnail.src = videoData.preview_url;
        videoThumbnail.style.display = 'block';
        videoThumbnail.alt = `Превью: ${videoData.title}`;
    } else if (videoThumbnail) {
        videoThumbnail.style.display = 'none';
    }
}

function displayFormats(formats) {
    if (!formatsList) return;
    
    formatsList.innerHTML = '';
    
    if (!formats || formats.length === 0) {
        formatsList.innerHTML = '<p>Для этой ссылки нет доступных видеоформатов.</p>';
        return;
    }
    
    const label = document.createElement('label');
    label.textContent = 'Качество';
    const select = document.createElement('select');
    formats.forEach((format, index) => {
        const quality = format.quality === 'unknown' ? 'Исходное качество' : format.quality;
        const size = format.filesize ? ' · ' + formatFileSize(format.filesize) : '';
        select.add(new Option(quality + size, index));
    });
    label.append(select);
    const download = document.createElement('button');
    download.className = 'primary';
    download.textContent = 'Скачать';
    download.addEventListener('click', async () => {
        const format = formats[Number(select.value)];
        download.disabled = true;
        try {
            await startDownload(format.video_format_id, format.audio_format_id);
        } finally {
            download.disabled = false;
        }
    });
    formatsList.append(label, download);
}

async function startDownload(videoFormatId, audioFormatId) {
    if (!currentVideoData) {
        showError('Данные о видео не найдены. Попробуйте заново получить форматы.');
        return;
    }
    const downloadData = {
        url: currentVideoData.url,
        video_format_id: videoFormatId,
        audio_format_id: audioFormatId
    };
    try {
        const response = await fetch('/api/start-download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(downloadData)
        });
        
        if (response.status === 409) await restoreActiveDownload();
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Ошибка ${response.status}: ${response.statusText}`);
        }
        
        const statusData = await response.json();
        trackDownload(statusData);
        cancelBtn.focus();
        showSuccess('');
        
    } catch (error) {
        console.error('Error starting download:', error);
        showError(`Ошибка при запуске скачивания: ${error.message}`);
    }
}

async function restoreActiveDownload() {
    try {
        const response = await fetch('/api/active-download', {cache: 'no-store'});
        if (!response.ok) return;
        const task = await response.json();
        if (task && !currentTaskId) trackDownload(task);
    } catch (error) {
        console.error('Could not restore active download:', error);
    }
}

function stopProgressTracking() {
    eventSource?.close();
    eventSource = null;
    clearInterval(progressInterval);
    progressInterval = null;
}

function trackDownload(task) {
    stopProgressTracking();
    currentTaskId = task.task_id;
    if (task.video && currentVideoData?.url !== task.video.url) {
        currentVideoData = task.video;
        displayVideoInfo(task.video);
        displayFormats(task.video.formats.filter(format => format.video_format_id));
    }
    downloadPercent.value = 0;
    downloadReadyContainer.hidden = true;
    cancelBtn.hidden = false;
    cancelBtn.disabled = false;
    showProgress();
    updateProgressDisplay(task);

    if (!window.EventSource) {
        startPollingFallback();
        return;
    }

    const source = new EventSource('/api/download-events/' + task.task_id);
    eventSource = source;
    source.onmessage = event => {
        if (eventSource === source) applyTaskStatus(JSON.parse(event.data));
    };
    source.onerror = () => {
        if (eventSource !== source) return;
        source.close();
        eventSource = null;
        startPollingFallback();
    };
}

function applyTaskStatus(task) {
    if (task.task_id !== currentTaskId) return;
    if (task.status === 'pending') {
        updateProgressDisplay(task);
        return;
    }
    stopProgressTracking();
    if (task.status === 'completed') {
        updateProgressDisplay(task);
        inspectorTitle.textContent = 'Файл готов';
        cancelBtn.hidden = true;
        downloadReadyBtn.href = '/api/get-video/' + task.task_id;
        downloadReadyBtn.removeAttribute('aria-disabled');
        downloadReadyBtn.removeAttribute('tabindex');
        downloadReadyBtn.textContent = 'Сохранить файл';
        backToFormats.disabled = false;
        downloadReadyContainer.hidden = false;
        if (progressSection.contains(document.activeElement) || document.activeElement === document.body) {
            downloadReadyBtn.focus();
        }
        return;
    }

    currentTaskId = null;
    if (currentVideoData) showResults();
    if (task.status === 'error') showError(task.description || 'Ошибка при скачивании');
    else if (task.status === 'canceled') showSuccess('Загрузка отменена.');
}

function startPollingFallback() {
    if (progressInterval) return;
    progressInterval = setInterval(checkDownloadProgress, 2000);
    checkDownloadProgress();
}

async function checkDownloadProgress() {
    const taskId = currentTaskId;
    if (!taskId) return;
    try {
        const response = await fetch('/api/download-status/' + taskId);
        if (taskId !== currentTaskId) return;
        if (response.ok) applyTaskStatus(await response.json());
        else if (response.status === 404) applyTaskStatus({task_id: taskId, status: 'error', description: 'Загрузка больше недоступна.'});
    } catch (error) {
        console.error('Could not refresh download status:', error);
    }
}

function updateProgressDisplay(task) {
    const ready = task.status === 'completed';
    const progress = Math.round(Number(task.percent) || 0);
    const percent = ready ? 100 : Math.min(99, Math.max(downloadPercent.value, progress));
    downloadPercent.value = percent;
    progressSection.style.setProperty('--download-angle', percent * 3.6 + 'deg');
    progressText.textContent = percent + '%';
    const stages = {
        'Downloading video track': 'Скачиваем видео',
        'Downloading audio track': 'Скачиваем звук',
        'Merging tracks': 'Собираем файл',
        'Merging parts': 'Собираем файл',
    };
    const label = ready ? 'Готово к сохранению' : stages[task.description] || 'Подготавливаем загрузку';
    if (statusText.textContent !== label) statusText.textContent = label;
    speedText.hidden = ready || !(task.speed_bps > 0);
    etaText.hidden = ready || task.eta_seconds == null || task.eta_seconds < 0;
    if (!speedText.hidden) speedText.textContent = formatSpeed(task.speed_bps);
    if (!etaText.hidden) etaText.textContent = 'Осталось ' + formatEta(task.eta_seconds);
}

function formatSpeed(bps) {
    const units = ['Б/с', 'КБ/с', 'МБ/с', 'ГБ/с'];
    let u = 0;
    let v = bps;
    while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
    return `${v.toFixed(1)} ${units[u]}`;
}

function formatEta(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    if (h > 0) return `${h}ч ${m.toString().padStart(2,'0')}м ${sec.toString().padStart(2,'0')}с`;
    if (m > 0) return `${m}м ${sec.toString().padStart(2,'0')}с`;
    return `${sec}с`;
}

async function cancelCurrentTask() {
    const taskId = currentTaskId;
    if (!taskId) return;
    cancelBtn.disabled = true;
    try {
        const response = await fetch('/api/cancel/' + taskId, {method: 'POST'});
        if (response.status === 409) {
            await checkDownloadProgress();
            return;
        }
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Не удалось отменить загрузку');
        }
        applyTaskStatus({task_id: taskId, status: 'canceled'});
    } catch (error) {
        showError(error.message || 'Ошибка при отмене');
    } finally {
        cancelBtn.disabled = false;
    }
}

function returnToFormats() {
    currentTaskId = null;
    saveStatusCheck = null;
    progressSection.classList.remove('is-returning');
    const shouldMoveFocus = progressSection.contains(document.activeElement);
    showResults();
    if (shouldMoveFocus) formatsList.querySelector('select')?.focus();
}

function finishFileDelivery(taskId) {
    if (saveStatusCheck !== taskId || currentTaskId !== taskId) return;
    statusText.textContent = 'Файл получен';
    inspectorTitle.textContent = 'Возвращаем параметры';
    progressSection.classList.add('is-returning');
    const delay = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 420;
    setTimeout(() => {
        if (saveStatusCheck === taskId && currentTaskId === taskId) returnToFormats();
    }, delay);
}

async function checkFileDelivery(taskId) {
    const isCurrent = () => saveStatusCheck === taskId && currentTaskId === taskId && !videoWorkspace.hidden && !progressSection.hidden;
    try {
        const response = await fetch('/api/download-status/' + taskId, {cache: 'no-store'});
        if (response.ok && (await response.json()).status === 'done' && isCurrent()) {
            finishFileDelivery(taskId);
            return;
        }
        if (response.status === 404) {
            if (saveStatusCheck === taskId) {
                saveStatusCheck = null;
                downloadReadyBtn.removeAttribute('aria-disabled');
                downloadReadyBtn.removeAttribute('tabindex');
                downloadReadyBtn.textContent = 'Сохранить файл';
                backToFormats.disabled = false;
                showError('Не удалось подтвердить передачу файла. Попробуйте ещё раз.');
            }
            return;
        }
    } catch (error) {
        console.error('Could not check file delivery:', error);
    }
    if (isCurrent()) {
        setTimeout(() => {
            if (isCurrent()) checkFileDelivery(taskId);
        }, 500);
    }
}

function showResults() {
    saveStatusCheck = null;
    progressSection.classList.remove('is-returning');
    videoWorkspace.hidden = false;
    inspectorTitle.textContent = 'Параметры файла';
    progressSection.hidden = true;
    resultsSection.hidden = false;
}

function hideResults() {
    saveStatusCheck = null;
    videoWorkspace.hidden = true;
}

function showProgress() {
    videoWorkspace.hidden = false;
    inspectorTitle.textContent = 'Загрузка файла';
    resultsSection.hidden = true;
    progressSection.hidden = false;
}

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (progressInterval) {
        clearInterval(progressInterval);
    }
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
});

// Handle paste in URL input
if (videoUrlInput) {
    videoUrlInput.addEventListener('paste', function(e) {
        // Небольшая задержка чтобы дать время тексту вставиться
        setTimeout(() => {
            const url = videoUrlInput.value.trim();
            if (url) {
                // Автоматически убираем лишние пробелы и символы
                videoUrlInput.value = url;
            }
        }, 10);
    });
}

// Navigation functions
function toggleMobileMenu() {
    if (!navMenu) return;
    
    const isActive = navMenu.classList.contains('active');
    
    if (isActive) {
        closeMobileMenu();
    } else {
        openMobileMenu();
    }
}

function openMobileMenu() {
    if (navMenu && navToggle) {
        navMenu.classList.add('active');
        navToggle.classList.add('active');
        
        // Prevent body scroll when menu is open
        document.body.style.overflow = 'hidden';
    }
}

function closeMobileMenu() {
    if (navMenu && navToggle) {
        navMenu.classList.remove('active');
        navToggle.classList.remove('active');
        
        // Restore body scroll
        document.body.style.overflow = '';
    }
}

// Handle window resize
window.addEventListener('resize', function() {
    // Close mobile menu on desktop view
    if (window.innerWidth > 768) {
        closeMobileMenu();
    }
});

// Handle escape key to close menu
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && navMenu && navMenu.classList.contains('active')) {
        closeMobileMenu();
    }
});


function mediaThumbnail(src, className) {
    const image = new Image();
    image.className = className;
    image.alt = '';
    image.loading = 'lazy';
    image.addEventListener('error', () => image.remove(), {once: true});
    image.src = src;
    return image;
}
