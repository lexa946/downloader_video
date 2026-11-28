// App state
let currentVideoData = null;
let currentDownload = null;
let startRequest = null;
let progressInterval = null;
let eventSource = null;
let saveStatusCheck = null;
const downloadStorageKey = 'signal.currentDownload';
const videoStorageKey = 'signal.videoParameters';

// DOM elements
const videoUrlInput = document.getElementById('videoUrl');
const analyzeBtn = document.getElementById('analyzeBtn');
const resultsSection = document.getElementById('results');
const progressSection = document.getElementById('progress');
const downloadAd = document.querySelector('.download-ad');
let downloadAdRequested = false;
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
        if (!currentDownload || saveStatusCheck) {
            event.preventDefault();
            return;
        }
        saveStatusCheck = currentDownload;
        downloadReadyBtn.setAttribute('aria-disabled', 'true');
        downloadReadyBtn.setAttribute('tabindex', '-1');
        downloadReadyBtn.textContent = 'Передаём файл…';
        backToFormats.disabled = true;
        statusText.textContent = 'Передаём файл в браузер';
        checkFileDelivery(currentDownload);
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
                localStorage.removeItem(videoStorageKey);
                if (!currentDownload) {
                    currentVideoData = null;
                    hideResults();
                }
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
    if (document.getElementById('consentBackdrop')?.hidden) restorePage();
});
document.addEventListener('cookie-consent-accepted', restorePage);

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
    if (currentDownload && !videoWorkspace.hidden && !progressSection.hidden && downloadReadyContainer.hidden) {
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
    
    resetDownload();
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
        if (videoUrlInput.value.trim() !== url) return;
        const saved = readVideoParameters(url);
        saveVideoParameters({url, video: videoData, selected: saved?.selected});
        renderVideoParameters(videoData, saved?.selected);
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

function restorePage() {
    restoreSavedDownload();
    if (!currentDownload && !currentVideoData && !analyzeBtn.disabled) {
        restoreVideoParameters();
    }
}

function readVideoParameters(url) {
    try {
        const saved = JSON.parse(localStorage.getItem(videoStorageKey));
        if (saved?.url === url && Array.isArray(saved.video?.formats)) return saved;
    } catch {
        // Повреждённая запись или недоступное хранилище.
    }
    return null;
}

function saveVideoParameters(parameters) {
    try {
        localStorage.setItem(videoStorageKey, JSON.stringify(parameters));
    } catch {
        // Параметры остаются доступны на текущей странице.
    }
}

function restoreVideoParameters() {
    const saved = readVideoParameters(videoUrlInput.value.trim());
    if (!saved) return;
    renderVideoParameters(saved.video, saved.selected);
    showResults();
}

function renderVideoParameters(video, selected) {
    currentVideoData = video;
    displayVideoInfo(video);
    displayFormats(video.formats.filter(format => format.video_format_id), selected);
}

function displayFormats(formats, selected) {
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
    const selectedIndex = formats.findIndex(format =>
        format.video_format_id === selected?.video && format.audio_format_id === selected?.audio
    );
    if (selectedIndex >= 0) select.value = String(selectedIndex);
    select.addEventListener('change', () => {
        const saved = readVideoParameters(videoUrlInput.value.trim());
        const format = formats[Number(select.value)];
        if (saved && saved.video.url === currentVideoData?.url && format) {
            saved.selected = {video: format.video_format_id, audio: format.audio_format_id};
            saveVideoParameters(saved);
        }
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
    if (startRequest) return;
    if (!currentVideoData) {
        showError('Данные о видео не найдены. Попробуйте заново получить форматы.');
        return;
    }
    const downloadData = {
        url: currentVideoData.url,
        video_format_id: videoFormatId,
        audio_format_id: audioFormatId
    };
    resetDownload();
    const request = {};
    startRequest = request;
    try {
        const response = await fetch('/api/start-download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(downloadData)
        });
        
        if (startRequest !== request) return;
        if (response.status === 409) await restoreActiveDownload(request);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Ошибка ${response.status}: ${response.statusText}`);
        }
        
        const statusData = await response.json();
        if (startRequest !== request) return;
        trackDownload(statusData, downloadData.url);
        cancelBtn.focus();
        showSuccess('');
        
    } catch (error) {
        if (startRequest !== request) return;
        console.error('Error starting download:', error);
        showError(`Ошибка при запуске скачивания: ${error.message}`);
    } finally {
        if (startRequest === request) startRequest = null;
    }
}

async function restoreActiveDownload(request) {
    try {
        const response = await fetch('/api/active-download', {cache: 'no-store'});
        if (!response.ok) return;
        const task = await response.json();
        if (task && startRequest === request) trackDownload(task, task.video.url);
    } catch (error) {
        console.error('Could not restore active download:', error);
    }
}

function restoreSavedDownload() {
    if (currentDownload || startRequest) return;
    let saved;
    try {
        saved = JSON.parse(sessionStorage.getItem(downloadStorageKey));
    } catch {
        // Хранилище может быть недоступно в настройках браузера.
    }
    if (!saved) return;
    if (typeof saved.taskId !== 'string' || typeof saved.url !== 'string' || validateUrl(saved.url)) {
        resetDownload();
        return;
    }
    const download = {taskId: saved.taskId, url: saved.url, restoring: true};
    currentDownload = download;
    restoreSourceUrl(download.url);
    showSuccess('Проверяем статус загрузки…');
    startPollingFallback();
}

function restoreSourceUrl(url) {
    videoUrlInput.value = url;
    videoUrlInput.dispatchEvent(new Event('input'));
}

function resetDownload() {
    stopProgressTracking();
    currentDownload = null;
    startRequest = null;
    saveStatusCheck = null;
    try {
        sessionStorage.removeItem(downloadStorageKey);
    } catch {
        // Загрузка работает и при отключённом хранилище.
    }
}

function stopProgressTracking() {
    eventSource?.close();
    eventSource = null;
    clearInterval(progressInterval);
    progressInterval = null;
}

function trackDownload(task, url) {
    currentDownload = {taskId: task.task_id, url};
    try {
        sessionStorage.setItem(downloadStorageKey, JSON.stringify(currentDownload));
    } catch {
        // Загрузка работает и при отключённом хранилище.
    }
    prepareDownloadScreen(task);
    if (task.status === 'pending') watchDownload(task.task_id);
    else applyTaskStatus(task);
}

function prepareDownloadScreen(task) {
    if (task.video && currentVideoData?.url !== task.video.url) {
        const saved = readVideoParameters(currentDownload.url);
        renderVideoParameters(task.video, saved?.selected);
    }
    downloadPercent.value = 0;
    downloadReadyContainer.hidden = true;
    cancelBtn.hidden = false;
    cancelBtn.disabled = false;
    progressSection.classList.remove('is-returning');
    showProgress();
    updateProgressDisplay(task);
}

function watchDownload(taskId) {
    if (!window.EventSource) {
        startPollingFallback();
        return;
    }

    const source = new EventSource('/api/download-events/' + encodeURIComponent(taskId));
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
    const download = currentDownload;
    if (!download || task.task_id !== download.taskId) return;
    if (task.status === 'done' || task.file_available === false) {
        showUnavailableDownload(download);
        return;
    }
    if (download.restoring) {
        download.restoring = false;
        showSuccess('');
        if (task.status === 'pending' || task.status === 'completed') {
            prepareDownloadScreen(task);
            if (task.status === 'pending' && window.EventSource) {
                stopProgressTracking();
                watchDownload(task.task_id);
            }
        }
    }
    if (task.status === 'pending') {
        if (downloadReadyContainer.hidden) updateProgressDisplay(task);
        return;
    }
    stopProgressTracking();
    if (task.status === 'completed') {
        updateProgressDisplay(task);
        inspectorTitle.textContent = 'Файл готов';
        cancelBtn.hidden = true;
        downloadReadyBtn.href = '/api/get-video/' + encodeURIComponent(task.task_id);
        downloadReadyBtn.removeAttribute('aria-disabled');
        downloadReadyBtn.removeAttribute('tabindex');
        downloadReadyBtn.textContent = 'Скачать';
        backToFormats.disabled = false;
        downloadReadyContainer.hidden = false;
        if (progressSection.contains(document.activeElement) || document.activeElement === document.body) {
            downloadReadyBtn.focus();
        }
        return;
    }

    resetDownload();
    if (currentVideoData) showResults();
    else restoreVideoParameters();
    if (task.status === 'error') showError(task.description || 'Ошибка при скачивании');
    else if (task.status === 'canceled') showSuccess('Загрузка отменена.');
}

function showUnavailableDownload(download) {
    resetDownload();
    currentVideoData = null;
    hideResults();
    switchTab('analyze');
    restoreSourceUrl(download.url);
    try {
        localStorage.setItem('lastVideoUrl', download.url);
    } catch {
        // Исходная ссылка уже восстановлена в форме.
    }
    showError('Загрузка или файл больше недоступны. Запустите загрузку заново.');
}

function startPollingFallback() {
    if (progressInterval) return;
    progressInterval = setInterval(checkDownloadProgress, 2000);
    checkDownloadProgress();
}

async function checkDownloadProgress() {
    const download = currentDownload;
    if (!download || download.checking) return;
    download.checking = true;
    try {
        const response = await fetch('/api/download-status/' + encodeURIComponent(download.taskId), {cache: 'no-store'});
        const task = response.ok ? await response.json() : null;
        if (download !== currentDownload) return;
        if (task) applyTaskStatus(task);
        else if (isDownloadUnavailable(response)) showUnavailableDownload(download);
    } catch (error) {
        console.error('Could not refresh download status:', error);
    } finally {
        download.checking = false;
    }
}

function isDownloadUnavailable(response) {
    return [400, 401, 403, 404, 410].includes(response.status);
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
    const download = currentDownload;
    if (!download) return;
    cancelBtn.disabled = true;
    try {
        const response = await fetch('/api/cancel/' + encodeURIComponent(download.taskId), {method: 'POST'});
        if (currentDownload !== download) return;
        if (response.status === 409) {
            await checkDownloadProgress();
            return;
        }
        if (isDownloadUnavailable(response)) {
            showUnavailableDownload(download);
            return;
        }
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Не удалось отменить загрузку');
        }
        applyTaskStatus({task_id: download.taskId, status: 'canceled'});
    } catch (error) {
        if (currentDownload === download) showError(error.message || 'Ошибка при отмене');
    } finally {
        if (currentDownload === download) cancelBtn.disabled = false;
    }
}

function returnToFormats() {
    resetDownload();
    const shouldMoveFocus = progressSection.contains(document.activeElement);
    showResults();
    if (shouldMoveFocus) formatsList.querySelector('select')?.focus();
}

function finishFileDelivery(download) {
    statusText.textContent = 'Файл получен';
    inspectorTitle.textContent = 'Возвращаем параметры';
    progressSection.classList.add('is-returning');
    const delay = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 420;
    setTimeout(() => {
        if (saveStatusCheck === download && currentDownload === download) returnToFormats();
    }, delay);
}

async function checkFileDelivery(download, fileWasMissing = false) {
    const isCurrent = () => saveStatusCheck === download && currentDownload === download;
    let fileMissing = false;
    try {
        const response = await fetch('/api/download-status/' + encodeURIComponent(download.taskId), {cache: 'no-store'});
        const task = response.ok ? await response.json() : null;
        if (!isCurrent()) return;
        if (task?.status === 'done') {
            finishFileDelivery(download);
            return;
        }
        // The server removes the delivered file just before recording 'done'.
        fileMissing = task?.file_available === false;
        if (isDownloadUnavailable(response) || (fileMissing && fileWasMissing)) {
            showUnavailableDownload(download);
            return;
        }
        if (task?.status === 'error' || task?.status === 'canceled') {
            applyTaskStatus(task);
            return;
        }
    } catch (error) {
        console.error('Could not check file delivery:', error);
    }
    if (isCurrent()) {
        setTimeout(() => {
            if (isCurrent()) checkFileDelivery(download, fileMissing);
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
    requestDownloadAd();
}

function requestDownloadAd() {
    if (!downloadAd || downloadAdRequested || !document.getElementById('consentBackdrop')?.hidden) return;

    downloadAdRequested = true;
    const banner = downloadAd.querySelector('.download-ad-banner');
    const label = downloadAd.querySelector('.download-ad-label');
    const hideAd = () => { downloadAd.hidden = true; };

    window.yaContextCb = window.yaContextCb || [];
    window.yaContextCb.push(() => {
        downloadAd.hidden = false;
        window.Ya.Context.AdvManager.render({
            blockId: 'R-A-16518515-5',
            renderTo: banner.id,
            onRender: () => { label.hidden = false; },
            onError: ({type}) => {
                if (type === 'error') hideAd();
            },
        });
    });
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
