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
    
    // Проверяем, находимся ли мы на странице парсера
    const parserPages = [
        '/youtube-downloader',
        '/instagram-downloader', 
        '/vk-downloader'
    ];
    
    if (parserPages.includes(currentPath)) {
        // Активируем dropdown toggle
        const dropdownToggle = document.querySelector('.dropdown-toggle');
        if (dropdownToggle) {
            dropdownToggle.classList.add('active');
        }
    }
}