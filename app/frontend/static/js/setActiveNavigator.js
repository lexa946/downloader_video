function setActiveNavigation() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll(".nav-link");

    navLinks.forEach(link => {
        // Пропускаем dropdown toggle, так как он не является прямой ссылкой
        if (link.classList.contains('dropdown-toggle')) {
            return;
        }
        
        if (link.pathname === currentPath) {
            link.classList.add("active");
        }
    });
    
    // Подсветка dropdown toggles по текущей странице
    const dropdowns = document.querySelectorAll('.dropdown');
    dropdowns.forEach(d => {
        const menu = d.querySelector('.dropdown-menu');
        const toggle = d.querySelector('.dropdown-toggle');
        if (!menu || !toggle) return;
        const link = menu.querySelector(`a[href="${currentPath}"]`);
        if (link) toggle.classList.add('active');
    });
}