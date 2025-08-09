document.addEventListener('DOMContentLoaded', function() {
  const currentPath = window.location.pathname;

  // Highlight active link inside any dropdown
  document.querySelectorAll('.dropdown').forEach(dropdown => {
    const menu = dropdown.querySelector('.dropdown-menu');
    if (menu) {
      const activeLink = menu.querySelector(`a[href="${currentPath}"]`);
      if (activeLink) {
        activeLink.classList.add('active');
        const toggle = dropdown.querySelector('.dropdown-toggle');
        if (toggle) toggle.classList.add('active');
      }
    }
  });

  // Toggle behavior for multiple dropdowns
  document.querySelectorAll('.dropdown-toggle').forEach(toggle => {
    toggle.addEventListener('click', function(e) {
      e.preventDefault();
      const parent = this.closest('.dropdown');
      if (!parent) return;
      const isActive = parent.classList.contains('active');

      // close others
      document.querySelectorAll('.dropdown.active').forEach(d => {
        if (d !== parent) d.classList.remove('active');
      });

      // toggle current
      if (isActive) parent.classList.remove('active');
      else parent.classList.add('active');
    });
  });

  // Close on outside click
  document.addEventListener('click', function(e) {
    const anyDropdown = e.target.closest('.dropdown');
    if (!anyDropdown) {
      document.querySelectorAll('.dropdown.active').forEach(d => d.classList.remove('active'));
    }
  });
});