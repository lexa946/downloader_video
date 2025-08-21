document.addEventListener('DOMContentLoaded', function() {
    const navToggle = document.getElementById('navToggle');
    const navMenu = document.getElementById('navMenu');
    const navBackdrop = document.getElementById('navBackdrop');

    console.log('Mobile nav script loaded');
    console.log('navToggle:', navToggle);
    console.log('navMenu:', navMenu);
    
    function setBodyScrollLocked(locked) {
        document.body.style.overflow = locked ? 'hidden' : '';
    }

    if (navToggle && navMenu) {
        navToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('Hamburger clicked!');
            const willOpen = !navToggle.classList.contains('active');
            navToggle.classList.toggle('active');
            navMenu.classList.toggle('active');
            if (navBackdrop) navBackdrop.classList.toggle('active');
            console.log('navMenu classes:', navMenu.className);

            if (window.innerWidth <= 768) {
                navMenu.style.display = willOpen ? 'block' : 'none';
                setBodyScrollLocked(willOpen);
            } else {
                navMenu.style.display = '';
                setBodyScrollLocked(false);
            }
        });
        
        // Закрываем мобильное меню только по клику на обычные ссылки, не на toggles
        const navLinks = navMenu.querySelectorAll('.nav-link:not(.dropdown-toggle), .dropdown-link');
        navLinks.forEach(link => {
            link.addEventListener('click', function() {
                if (window.innerWidth <= 768) {
                    navToggle.classList.remove('active');
                    navMenu.classList.remove('active');
                    if (navBackdrop) navBackdrop.classList.remove('active');
                    navMenu.style.display = 'none';
                    setBodyScrollLocked(false);
                }
            });
        });
        
        document.addEventListener('click', function(e) {
            if (!navToggle.contains(e.target) && !navMenu.contains(e.target)) {
                navToggle.classList.remove('active');
                navMenu.classList.remove('active');
                if (navBackdrop) navBackdrop.classList.remove('active');
                navMenu.style.display = 'none';
                setBodyScrollLocked(false);
            }
        });
        
        window.addEventListener('resize', function() {
            if (window.innerWidth > 768) {
                navToggle.classList.remove('active');
                navMenu.classList.remove('active');
                if (navBackdrop) navBackdrop.classList.remove('active');
                navMenu.style.display = '';
                setBodyScrollLocked(false);
            }
        });

        if (navBackdrop) {
            navBackdrop.addEventListener('click', function() {
                navToggle.classList.remove('active');
                navMenu.classList.remove('active');
                navBackdrop.classList.remove('active');
                navMenu.style.display = 'none';
                setBodyScrollLocked(false);
            });
        }
    }
});
