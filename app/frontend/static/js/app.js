// App state
let currentVideoData = null;
let currentTaskId = null;
let progressInterval = null;
let eventSource = null;

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
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const statusText = document.getElementById('statusText');
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

// History elements
const historySection = document.getElementById('historySection');
const historyList = document.getElementById('historyList');
const historyEmpty = document.getElementById('historyEmpty');

// Download ready elements  
const downloadReadyContainer = document.getElementById('downloadReadyContainer');
const downloadReadyBtn = document.getElementById('downloadReadyBtn');

// Clear input elements
const clearInputBtn = document.getElementById('clearInput');
const startTimeInput = document.getElementById('startTime');
const endTimeInput = document.getElementById('endTime');
const clipForm = document.getElementById('clipForm');
const clearStartTimeBtn = document.getElementById('clearStartTime');
const clearEndTimeBtn = document.getElementById('clearEndTime');

// Event listeners
document.addEventListener('DOMContentLoaded', function() {

    setActiveNavigation();

    // Video functionality
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', handleAnalyzeVideo);
    }
    
    if (videoUrlInput) {
        videoUrlInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                handleAnalyzeVideo();
            }
        });
    }
    
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
    // YouTube search
    if (searchBtn && ytSearchQuery) {
        searchBtn.addEventListener('click', handleYoutubeSearch);
        ytSearchQuery.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') handleYoutubeSearch();
        });
    }
    if (clearSearchBtn && ytSearchQuery) {
        clearSearchBtn.addEventListener('click', () => {
            ytSearchQuery.value = '';
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
        videoUrlInput.focus();
    }
    
    // Load user history
    loadUserHistory();
    
    // Обработчик кнопки скачивания готового файла
    if (downloadReadyBtn) {
        downloadReadyBtn.addEventListener('click', () => {
            if (currentTaskId) {
                console.log('Manual download triggered');
                downloadCompletedFile();
            }
        });
    }
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
function showError(message) {
    const existingError = document.querySelector('.error-message');
    if (existingError) {
        existingError.remove();
    }
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message fade-in';
    errorDiv.textContent = message;
    
    const downloadSection = document.querySelector('.download-section');
    if (downloadSection) {
        downloadSection.appendChild(errorDiv);
        
        // Убираем ошибку через 5 секунд
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.remove();
            }
        }, 5000);
    }
}

function showSuccess(message) {
    const existingSuccess = document.querySelector('.success-message');
    if (existingSuccess) {
        existingSuccess.remove();
    }
    
    const successDiv = document.createElement('div');
    successDiv.className = 'success-message fade-in';
    successDiv.textContent = message;
    
    const downloadSection = document.querySelector('.download-section');
    if (downloadSection) {
        downloadSection.appendChild(successDiv);
        
        // Убираем сообщение через 3 секунды
        setTimeout(() => {
            if (successDiv.parentNode) {
                successDiv.remove();
            }
        }, 3000);
    }
}

function switchTab(tab) {
    tabButtons.forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
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
    
    const supportedPlatforms = [
        'youtube.com', 'youtu.be', 'www.youtube.com',
        'instagram.com', 'www.instagram.com',
        'vk.com', 'www.vk.com', 'vkvideo.ru',
        'rutube.ru', 'www.rutube.ru',
        'tiktok.com', 'www.tiktok.com', 'vt.tiktok.com'
    ];
    
    const isSupported = supportedPlatforms.some(platform => 
        url.toLowerCase().includes(platform)
    );
    
    if (!isSupported) {
        return 'Данная платформа не поддерживается. Поддерживаются: YouTube, Instagram*, VK, VK Video, RuTube, TikTok';
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

function parseHmsToSeconds(val) {
    if (val === undefined || val === null) return null;
    const s = String(val).trim();
    if (!s) return null;
    const m = s.match(/^\d{2}:\d{2}:\d{2}$/);
    if (!m) return null;
    const [hh, mm, ss] = s.split(':').map(Number);
    if (mm >= 60 || ss >= 60) return null;
    return hh * 3600 + mm * 60 + ss;
}

function formatDigitsToHMS(digits) {
    // Fill from right: SS, then MM, then HH
    const raw = digits.replace(/[^0-9]/g, '').slice(-6); // keep last 6 digits
    const pad = raw.padStart(6, '0');
    const hh = pad.slice(0, 2);
    let mm = pad.slice(2, 4);
    let ss = pad.slice(4, 6);
    // clamp to valid ranges to avoid invalid values during typing
    if (Number(mm) > 59) mm = '59';
    if (Number(ss) > 59) ss = '59';
    return `${hh}:${mm}:${ss}`;
}

function attachHMSBehavior(input) {
    if (!input) return;
    // keep a separate buffer of digits per input
    const ensureBuffer = () => {
        if (typeof input.dataset.dbuf !== 'string') input.dataset.dbuf = '';
    };
    const renderFromBuffer = () => {
        const formatted = formatDigitsToHMS(input.dataset.dbuf || '');
        input.value = formatted;
        try { input.setSelectionRange(formatted.length, formatted.length); } catch (_) {}
    };
    const initFromValue = () => {
        const digits = (input.value || '').replace(/[^0-9]/g, '');
        input.dataset.dbuf = digits.slice(-6);
        renderFromBuffer();
    };

    ensureBuffer();
    initFromValue();

    input.addEventListener('keydown', (e) => {
        ensureBuffer();
        // allow navigation keys
        const navKeys = ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Tab','Home','End'];
        if (navKeys.includes(e.key)) return;
        if (e.key === 'Backspace') {
            e.preventDefault();
            // remove last digit (rightmost)
            input.dataset.dbuf = (input.dataset.dbuf || '').slice(0, -1);
            renderFromBuffer();
            return;
        }
        if (e.key === 'Delete') {
            e.preventDefault();
            // behave same as backspace for simplicity
            input.dataset.dbuf = (input.dataset.dbuf || '').slice(0, -1);
            renderFromBuffer();
            return;
        }
        if (/^[0-9]$/.test(e.key)) {
            e.preventDefault();
            const cur = (input.dataset.dbuf || '') + e.key;
            // keep last 6 digits only
            input.dataset.dbuf = cur.slice(-6);
            renderFromBuffer();
            return;
        }
        // block any other input
        e.preventDefault();
    });

    input.addEventListener('input', () => {
        // In case some browsers still emit input, normalize back to buffer rendering
        renderFromBuffer();
    });
    input.addEventListener('paste', (e) => {
        e.preventDefault();
        const text = (e.clipboardData || window.clipboardData).getData('text');
        const digits = text.replace(/[^0-9]/g, '');
        input.dataset.dbuf = digits.slice(-6);
        renderFromBuffer();
    });
    input.addEventListener('keypress', (e) => {
        // allow digits only; colon is managed by formatter
        if (!/[0-9]/.test(e.key)) {
            e.preventDefault();
        }
    });
    input.addEventListener('blur', () => {
        // if user left partially filled (like 12:3:), reformat/correct
        renderFromBuffer();
    });
}

attachHMSBehavior(startTimeInput);
attachHMSBehavior(endTimeInput);

// Toggle clip form visibility with slide effect via CSS class
if (clipForm) {
    // use details/open to drive state; animate via CSS if needed
    const syncOpen = () => {
        clipForm.dataset.open = clipForm.open ? 'true' : 'false';
    };
    clipForm.addEventListener('toggle', syncOpen);
    syncOpen();
}

// Clear buttons for time inputs
if (clearStartTimeBtn && startTimeInput) {
    clearStartTimeBtn.addEventListener('click', () => {
        // reset buffer and visual to 00:00:00
        startTimeInput.dataset.dbuf = '';
        startTimeInput.value = '00:00:00';
        startTimeInput.focus();
        try { startTimeInput.setSelectionRange(startTimeInput.value.length, startTimeInput.value.length); } catch(_) {}
    });
}
if (clearEndTimeBtn && endTimeInput) {
    clearEndTimeBtn.addEventListener('click', () => {
        endTimeInput.dataset.dbuf = '';
        endTimeInput.value = '00:00:00';
        endTimeInput.focus();
        try { endTimeInput.setSelectionRange(endTimeInput.value.length, endTimeInput.value.length); } catch(_) {}
    });
}

function setButtonLoading(button, isLoading) {
    if (!button) return;
    
    const btnText = button.querySelector('.btn-text');
    const btnLoader = button.querySelector('.btn-loader');
    
    if (btnText && btnLoader) {
        if (isLoading) {
            btnText.style.display = 'none';
            btnLoader.style.display = 'inline';
            button.disabled = true;
        } else {
            btnText.style.display = 'inline';
            btnLoader.style.display = 'none';
            button.disabled = false;
        }
    }
}

// Main functions
async function handleAnalyzeVideo() {
    if (!videoUrlInput) return;
    
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
    setButtonLoading(analyzeBtn, true);
    hideResults();
    hideProgress();
    
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
        displayFormats(videoData.formats);
        showResults();
        
        showSuccess('Форматы видео успешно получены!');
        
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
    items.forEach(item => {
        const div = document.createElement('div');
        div.className = 'format-item yt-result';
        const thumb = item.thumbnail_url ? `<img loading="lazy" src="${item.thumbnail_url}" alt="Preview" class="yt-thumb" onerror="this.style.display='none'">` : '';
        const duration = item.duration ? `<div class="yt-duration">${formatDuration(item.duration)}</div>` : '';
        const author = item.author ? `<div class="yt-author">${item.author}</div>` : '';
        div.innerHTML = `
            ${thumb}
            <div class="yt-title">${item.title || ''}</div>
            ${author}
            ${duration}
            <button type="button" class="download-format-btn yt-open-btn" data-url="${item.video_url}">Открыть</button>
        `;
        const openBtn = div.querySelector('button');
        openBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (videoUrlInput) {
                videoUrlInput.value = item.video_url;
                localStorage.setItem('lastVideoUrl', item.video_url);
                // переключаем на вкладку форматов
                switchTab('analyze');
                handleAnalyzeVideo();
                // не очищаем результаты, чтобы сохранить выдачу
                resultsSection.scrollIntoView({behavior: 'smooth'});
            } else {
                window.open(item.video_url, '_blank');
            }
        });
        // click anywhere selects
        div.addEventListener('click', (e) => {
            if (e.target.tagName.toLowerCase() === 'button') return;
            if (videoUrlInput) {
                videoUrlInput.value = item.video_url;
                localStorage.setItem('lastVideoUrl', item.video_url);
                switchTab('analyze');
                handleAnalyzeVideo();
                resultsSection.scrollIntoView({behavior: 'smooth'});
            }
        });
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
        formatsList.innerHTML = '<p>Форматы не найдены</p>';
        return;
    }
    
    // Сортируем форматы по качеству (сначала лучшие)
    const sortedFormats = formats.sort((a, b) => {
        const qualityOrder = {
            '2160p': 6, '1440p': 5, '1080p': 4, 
            '720p': 3, '480p': 2, '360p': 1, '240p': 0
        };
        
        const aQuality = qualityOrder[a.quality] || -1;
        const bQuality = qualityOrder[b.quality] || -1;
        
        return bQuality - aQuality;
    });
    
    sortedFormats.forEach(format => {
        const formatElement = createFormatElement(format);
        formatsList.appendChild(formatElement);
    });
}

function createFormatElement(format) {
    const formatDiv = document.createElement('div');
    formatDiv.className = 'format-item';
    
    const isAudioOnly = format.quality.toLowerCase().includes('audio') || 
                       format.quality.toLowerCase().includes('mp3');
    
    const qualityDisplay = isAudioOnly ? 
        `🎵 ${format.quality} (Только аудио)` : 
        `🎥 ${format.quality}`;
    
    formatDiv.innerHTML = `
        <div class="format-quality">${qualityDisplay}</div>
        ${format.filesize && format.filesize > 0 ? `<div class="format-size">${formatFileSize(format.filesize)}</div>` : ''}
        <button class="download-format-btn" onclick="startDownload('${format.video_format_id}', '${format.audio_format_id}')">
            ${isAudioOnly ? 'Скачать аудио' : 'Скачать видео'}
        </button>
    `;
    
    // Добавляем клик на всю карточку
    formatDiv.addEventListener('click', (e) => {
        // Не срабатывает если кликнули по кнопке
        if (e.target.classList.contains('download-format-btn')) return;
        
        // Вызываем ту же логику что и кнопка
        startDownload(format.video_format_id, format.audio_format_id);
    });
    
    return formatDiv;
}

async function startDownload(videoFormatId, audioFormatId) {
    if (!currentVideoData) {
        showError('Данные о видео не найдены. Попробуйте заново получить форматы.');
        return;
    }
    const clipEnabled = clipForm && clipForm.dataset.open === 'true';
    const rawStart = startTimeInput ? startTimeInput.value.trim() : '';
    const rawEnd = endTimeInput ? endTimeInput.value.trim() : '';
    const start_seconds = clipEnabled && rawStart ? parseHmsToSeconds(rawStart) : null;
    const end_seconds = clipEnabled && rawEnd ? parseHmsToSeconds(rawEnd) : null;

    if (clipEnabled) {
        if (rawStart && start_seconds == null) {
            showError('Неверный формат начала. Используйте ЧЧ:ММ:СС');
            return;
        }
        if (rawEnd && end_seconds == null) {
            showError('Неверный формат конца. Используйте ЧЧ:ММ:СС');
            return;
        }
        if (start_seconds != null && end_seconds != null && end_seconds <= start_seconds) {
            showError('Конец должен быть позже начала');
            return;
        }

        const duration = currentVideoData && typeof currentVideoData.duration === 'number' ? currentVideoData.duration : null;
        if (duration != null) {
            if (start_seconds != null && start_seconds > duration) {
                showError('Начало выходит за пределы длительности видео');
                return;
            }
            if (end_seconds != null && end_seconds > duration) {
                showError('Конец выходит за пределы длительности видео');
                return;
            }
        }
    }

    const downloadData = {
        url: currentVideoData.url,
        video_format_id: videoFormatId,
        audio_format_id: audioFormatId,
        start_seconds: start_seconds,
        end_seconds: end_seconds
    };
    if (downloadData.start_seconds == null) delete downloadData.start_seconds;
    if (downloadData.end_seconds == null) delete downloadData.end_seconds;
    
    try {
        const response = await fetch('/api/start-download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(downloadData)
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Ошибка ${response.status}: ${response.statusText}`);
        }
        
        const statusData = await response.json();
        currentTaskId = statusData.task_id;
        await loadUserHistory();
        showProgress();
        hideResults();
        startProgressTracking();

        showSuccess('Скачивание началось!');
        
    } catch (error) {
        console.error('Error starting download:', error);
        showError(`Ошибка при запуске скачивания: ${error.message}`);
    }
}

function startProgressTracking() {
    // Cleanup previous trackers
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
    // Prefer SSE if available
    if (window.EventSource) {
        startSSE();
    } else {
        startPollingFallback();
    }
    if (cancelBtn) {
        cancelBtn.disabled = false;
        cancelBtn.style.display = 'inline-block';
    }
}

function startSSE() {
    if (!currentTaskId) return;
    const url = `/api/download-events/${currentTaskId}`;
    eventSource = new EventSource(url);

    eventSource.onmessage = (e) => {
        try {
            const statusData = JSON.parse(e.data);
            updateProgressDisplay(statusData);
            if (statusData.status === 'completed') {
                if (downloadReadyContainer) {
                    downloadReadyContainer.style.display = 'block';
                }
                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                }
                loadUserHistory();
                hideProgress();
                if (cancelBtn) cancelBtn.style.display = 'none';
            } else if (statusData.status === 'canceled') {
                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                }
                showError('Загрузка отменена');
                hideProgress();
                showResults();
                if (cancelBtn) cancelBtn.style.display = 'none';
                loadUserHistory();
            } else if (statusData.status === 'error') {
                if (eventSource) {
                    eventSource.close();
                    eventSource = null;
                }
                showError(statusData.description || 'Произошла ошибка при скачивании');
                hideProgress();
                showResults();
                if (cancelBtn) cancelBtn.style.display = 'none';
            }
        } catch (err) {
            console.error('SSE parse error:', err);
        }
    };

    eventSource.onerror = () => {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        startPollingFallback();
    };
}

function startPollingFallback() {
    progressInterval = setInterval(checkDownloadProgress, 1000);
    checkDownloadProgress(); // Первая проверка сразу
}

async function checkDownloadProgress() {
    if (!currentTaskId) return;
    
    try {
        const response = await fetch(`/api/download-status/${currentTaskId}`);
        
        if (!response.ok) {
            throw new Error(`Ошибка ${response.status}: ${response.statusText}`);
        }
        
        const statusData = await response.json();
        
        updateProgressDisplay(statusData);
        console.log(statusData.status)
        if (statusData.status === 'completed') {
            clearInterval(progressInterval);
            progressInterval = null;
            console.log('Video completed download.');
            if (downloadReadyContainer) {
                downloadReadyContainer.style.display = 'block';
            }
            await loadUserHistory();
            hideProgress();
        } else if (statusData.status === 'canceled') {
            clearInterval(progressInterval);
            progressInterval = null;
            showError('Загрузка отменена');
            hideProgress();
            showResults();
            await loadUserHistory();
        } else if (statusData.status === 'error') {
            clearInterval(progressInterval);
            progressInterval = null;
            showError(statusData.description || 'Произошла ошибка при скачивании');
            hideProgress();
            showResults();
        }
    } catch (error) {
        console.error('Error checking progress:', error);
        clearInterval(progressInterval);
        progressInterval = null;
        showError(`Ошибка при проверке статуса: ${error.message}`);
    }
}

function updateProgressDisplay(statusData) {
    const percent = Math.round(statusData.percent || 0);
    
    if (progressFill) progressFill.style.width = `${percent}%`;
    if (progressText) progressText.textContent = `${percent}%`;
    
    const statusMessages = {
        'pending': 'Подготовка к скачиванию...',
        'downloading': 'Скачивание видео...',
        'processing': 'Обработка файла...',
        'completed': 'Скачивание завершено!',
        'error': 'Произошла ошибка',
        'canceled': 'Отменено пользователем'
    };
    
    if (statusText) {
        statusText.textContent = statusData.description || 
                                statusMessages[statusData.status] || 
                                'Выполняется...';
    }
}

async function cancelCurrentTask() {
    if (!currentTaskId) return;
    try {
        const response = await fetch(`/api/cancel/${currentTaskId}`, {
            method: 'POST'
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Не удалось отменить загрузку');
        }
        showSuccess('Отменяем загрузку...');
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        hideProgress();
        showResults();
        if (cancelBtn) cancelBtn.style.display = 'none';
        await loadUserHistory();
    } catch (e) {
        showError(e.message || 'Ошибка при отмене');
    }
}

async function downloadCompletedFile() {
    if (!currentTaskId) {
        console.error('No currentTaskId for download');
        return;
    }
    
    console.log(`Starting automatic download for task: ${currentTaskId}`);
    
    try {
         const downloadUrl = `/api/get-video/${currentTaskId}`;


        console.log('Trying direct link method...');
        window.open(downloadUrl, '_blank');

        showSuccess('Файл готов к скачиванию! Проверьте загрузки браузера.');

        
        // Показываем возможность скачать снова
        setTimeout(() => {
            showResults();
            downloadReadyContainer.style.display = 'none';
        }, 2000);
        
    } catch (error) {
        console.error('Error downloading file:', error);
        showError(`Ошибка при скачивании файла: ${error.message}`);
    }
}

function showResults() {
    if (resultsSection) {
        resultsSection.style.display = 'block';
        resultsSection.classList.add('fade-in');
    }
}

function hideResults() {
    if (resultsSection) {
        resultsSection.style.display = 'none';
        resultsSection.classList.remove('fade-in');
    }
    if (downloadReadyContainer) {
        downloadReadyContainer.style.display = 'none';
    }
}

function showProgress() {
    if (progressSection) {
        progressSection.style.display = 'block';
        progressSection.classList.add('fade-in');
    }
}

function hideProgress() {
    if (progressSection) {
        progressSection.style.display = 'none';
        progressSection.classList.remove('fade-in');
    }
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

// History functions
function getUserId() {
    // Get user_id from cookies
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'user_id') {
            return value;
        }
    }
    return null;
}

async function loadUserHistory() {
    const userId = getUserId();
    if (!userId || !historySection) {
        return;
    }
    
    try {
        const response = await fetch(`/user/${userId}/history`);
        if (!response.ok) {
            // If user not found or no history, hide section
            if (response.status === 404) {
                return;
            }
            throw new Error(`HTTP ${response.status}`);
        }
        
        const historyData = await response.json();
        
        if (historyData.history && historyData.history.length > 0) {
            const history = historyData.history;
            displayHistory(history);
            if (historySection) {
                historySection.style.display = 'block';
                historySection.classList.add('fade-in');
            }
        } else {
            historySection.style.display = 'block';
            historySection.classList.add('fade-in');
            historyEmpty.style.display = 'block';
        }
        
    } catch (error) {
        console.error('Error loading history:', error);
        // Don't show error to user for history - it's not critical
    }
}

function displayHistory(historyItems) {
    if (!historyList || !historyEmpty) return;
    
    historyList.innerHTML = '';
    
    if (historyItems.length === 0) {
        historyEmpty.style.display = 'block';
        return;
    }
    
    historyEmpty.style.display = 'none';
    
    historyItems.forEach(item => {
        const historyElement = createHistoryElement(item);
        historyList.appendChild(historyElement);
    });
}

function createHistoryElement(videoStatus) {
    const div = document.createElement('div');
    div.className = `history-item ${videoStatus.status}`;
    
    const video = videoStatus.video;
    const statusInfo = getStatusInfo(videoStatus.status);
    
    div.innerHTML = `
        <div class="history-video-info">
            ${video.preview_url ? 
                `<img src="${video.preview_url}" alt="Превью" class="history-thumbnail" onerror="this.style.display='none'">` : 
                `<div class="history-thumbnail"></div>`
            }
            <div class="history-details">
                <div class="history-title">${video.title || 'Без названия'}</div>
                ${video.author ? `<div class="history-author">Автор: ${video.author}</div>` : ''}
            </div>
        </div>
        
        <div class="history-actions">
            ${createHistoryActions(videoStatus)}
        </div>
    `;
    
    // Добавляем клик на карточку для запроса форматов
    div.addEventListener('click', (e) => {
        // Не срабатывает если кликнули по кнопке действия
        if (e.target.classList.contains('history-btn') || e.target.closest('.history-actions')) return;
        
        // Заполняем поле ввода URL из истории
        if (videoUrlInput && videoStatus.video.url) {
            videoUrlInput.value = videoStatus.video.url;
            localStorage.setItem('lastVideoUrl', videoStatus.video.url);
            
            // Запрашиваем форматы
            handleAnalyzeVideo();
            
            // Скроллим к началу страницы
            resultsSection.scrollIntoView()
            // window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });
    
    return div;
}

function getStatusInfo(status) {
    const statusMap = {
        'completed': { icon: '✅', text: 'Готово' },
        'downloading': { icon: '⬇️', text: 'Скачивается' },
        'pending': { icon: '⏳', text: 'Ожидание' },
        'processing': { icon: '⚙️', text: 'Обработка' },
        'error': { icon: '❌', text: 'Ошибка' }
    };
    
    return statusMap[status] || { icon: '❓', text: 'Неизвестно' };
}

function createHistoryActions(videoStatus) {
    let actions = '';

    const status = videoStatus.status.toLowerCase();
    
    if (status === 'completed') {
        actions += `
            <button class="history-btn download" onclick="downloadHistoryFile('${videoStatus.task_id}')">
                <span>📥</span> Скачать файл
            </button>
        `;
    }
    
    if (status === 'error' || status === 'done') {
        actions += `
            <button class="history-btn redownload" onclick="redownloadVideo('${videoStatus.video.url}')">
                <span>🔄</span> Заново
            </button>
        `;
    }
    
    if (status === 'pending') {
        actions += `
            <button class="history-btn info" onclick="resumeHistoryProgress('${videoStatus.task_id}')">
                <span>ℹ️</span> Загрузка
            </button>
        `;
    }
    if (status === 'pending' || status === 'downloading' || status === 'processing') {
        actions += `
            <button class="history-btn danger" onclick="cancelHistoryTask('${videoStatus.task_id}')">
                <span>🛑</span> Отменить
            </button>
        `;
    }
    
    return actions;
}

async function cancelHistoryTask(taskId) {
    try {
        const response = await fetch(`/api/cancel/${taskId}`, { method: 'POST' });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || 'Не удалось отменить задачу');
        }
        showSuccess('Загрузка отменена');
        await loadUserHistory();
        if (currentTaskId === taskId) {
            if (eventSource) { eventSource.close(); eventSource = null; }
            hideProgress();
            showResults();
            if (cancelBtn) cancelBtn.style.display = 'none';
        }
    } catch (e) {
        showError(e.message || 'Ошибка при отмене');
    }
}

async function downloadHistoryFile(taskId) {
    try {
        // Create download link
        const downloadUrl = `/api/get-video/${taskId}`;
        window.open(downloadUrl, '_blank');
        
        showSuccess('Файл начал скачиваться!');
        await loadUserHistory();
        
    } catch (error) {
        console.error('Error downloading file:', error);
        showError('Ошибка при скачивании файла');
    }
}

async function redownloadVideo(videoUrl) {
    // Fill URL input and trigger analysis
    if (videoUrlInput) {
        videoUrlInput.value = videoUrl;
        
        // Scroll to top
        window.scrollTo({ top: 0, behavior: 'smooth' });
        
        // Trigger analysis after scroll
        setTimeout(() => {
            handleAnalyzeVideo();
        }, 500);
        
        showSuccess('Ссылка вставлена! Начинаем анализ...');
    }
}

async function checkHistoryStatus(taskId) {
    try {
        const response = await fetch(`/api/download-status/${taskId}`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const statusData = await response.json();
        const statusInfo = getStatusInfo(statusData.status);
        const percent = Math.round(statusData.percent || 0);
        
        let message = `Статус: ${statusInfo.text}`;
        if (percent > 0) {
            message += ` (${percent}%)`;
        }
        if (statusData.description) {
            message += `\n${statusData.description}`;
        }
        
        alert(message);
        
        // Refresh history if status changed
        await loadUserHistory();
        
    } catch (error) {
        console.error('Error checking status:', error);
        showError('Не удалось получить статус скачивания');
    }
}

// Resume tracking of an existing task from history: show standard progress UI and keep updating
function resumeHistoryProgress(taskId) {
    try {
        currentTaskId = taskId;
        showProgress();
        hideResults();
        startProgressTracking();
    } catch (error) {
        console.error('Error resuming progress:', error);
        showError('Не удалось возобновить отслеживание прогресса');
    }
}

function formatDate(date) {
    const now = new Date();
    const diffInMinutes = Math.floor((now - date) / (1000 * 60));
    
    if (diffInMinutes < 1) {
        return 'Только что';
    } else if (diffInMinutes < 60) {
        return `${diffInMinutes} мин назад`;
    } else if (diffInMinutes < 1440) { // 24 hours
        const hours = Math.floor(diffInMinutes / 60);
        return `${hours} ч назад`;
    } else {
        return date.toLocaleDateString('ru-RU', {
            day: 'numeric',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit'
        });
    }
}

// Refresh history when download completes
function refreshHistoryOnComplete() {
    setTimeout(() => {
        loadUserHistory();
    }, 1000);
}