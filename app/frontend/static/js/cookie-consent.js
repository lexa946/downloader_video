(() => {
    const backdrop = document.getElementById('consentBackdrop');
    const settings = document.getElementById('cookieSettings');
    if (!backdrop) {
        settings?.addEventListener('click', () => { location.href = '/?cookie-settings=1'; });
        return;
    }

    const dialog = backdrop.querySelector('.consent-dialog');
    const accept = document.getElementById('acceptCookies');
    const decline = document.getElementById('declineCookies');
    const declined = document.getElementById('consentDeclined');
    const page = [document.querySelector('.mast'), document.getElementById('content'), document.querySelector('.foot')];

    function show() {
        backdrop.hidden = false;
        page.forEach(element => { element.inert = true; });
        declined.hidden = localStorage.getItem('cookieChoice') !== 'declined';
        accept.focus();
    }

    function hide() {
        backdrop.hidden = true;
        page.forEach(element => { element.inert = false; });
        settings.focus();
    }

    backdrop.addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        const controls = [...dialog.querySelectorAll('a, button')];
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });

    async function choose(accepted) {
        accept.disabled = true;
        decline.disabled = true;
        try {
            const response = await fetch('/api/cookie-consent', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({accepted})
            });
            if (!response.ok) throw new Error('Не удалось сохранить выбор. Попробуйте ещё раз.');
            localStorage.setItem('cookieChoice', accepted ? 'accepted' : 'declined');
            if (accepted) {
                hide();
                document.dispatchEvent(new Event('cookie-consent-accepted'));
            } else {
                show();
            }
        } catch (error) {
            declined.hidden = false;
            declined.textContent = error.message;
        } finally {
            accept.disabled = false;
            decline.disabled = false;
        }
    }

    accept.addEventListener('click', () => choose(true));
    decline.addEventListener('click', () => choose(false));
    settings.addEventListener('click', show);
    show();
    fetch('/api/cookie-consent', {cache: 'no-store'})
        .then(response => response.json())
        .then(state => {
            if (state.accepted && !new URLSearchParams(location.search).has('cookie-settings')) {
                hide();
                document.dispatchEvent(new Event('cookie-consent-accepted'));
            }
        })
        .catch(() => { declined.hidden = false; declined.textContent = 'Не удалось проверить настройки cookie. Обновите страницу.'; });
})();
