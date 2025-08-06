function setActiveNavigation() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll(".nav-link");

    navLinks.forEach(link => {
        if (link.pathname === currentPath) {
            link.classList.add("active")
        }
    });
}