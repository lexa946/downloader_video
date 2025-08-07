document.addEventListener('DOMContentLoaded', function() {
    const dropdown = document.querySelector('.dropdown');
    const dropdownToggle = document.querySelector('.dropdown-toggle');
    const dropdownMenu = document.querySelector('.dropdown-menu');
    
    // Определяем текущую страницу
    const currentPath = window.location.pathname;
    const parserPages = [
        '/youtube-downloader',
        '/instagram-downloader', 
        '/vk-downloader'
    ];
    
    // Проверяем, находимся ли мы на странице парсера
    const isOnParserPage = parserPages.includes(currentPath);
    
    // Если мы на странице парсера, подсвечиваем активную ссылку в dropdown
    if (isOnParserPage) {
        // Находим и подсвечиваем активную ссылку в dropdown
        const activeLink = dropdownMenu.querySelector(`a[href="${currentPath}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }
    }
    
    // Обработчик клика по dropdown toggle
    dropdownToggle.addEventListener('click', function(e) {
        e.preventDefault();
        dropdown.classList.toggle('active');
    });
    
    // Закрытие dropdown при клике вне его
    document.addEventListener('click', function(e) {
        if (!dropdown.contains(e.target)) {
            dropdown.classList.remove('active');
        }
    });
    
    // Обработчик наведения мыши
    dropdown.addEventListener('mouseenter', function() {
        if (isOnParserPage) {
            dropdown.classList.add('active');
        }
    });
    
    // Закрытие dropdown при выходе мыши за границы
    dropdown.addEventListener('mouseleave', function() {
        dropdown.classList.remove('active');
    });
}); 