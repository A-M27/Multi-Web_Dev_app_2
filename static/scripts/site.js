function showAlert(alertId = 'noCardsAlert') {
    const alert = document.getElementById(alertId);
    if (alert) {
        alert.style.display = 'block';
        setTimeout(() => {
            alert.style.display = 'none';
        }, 3000);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const menuToggleBtn = document.getElementById('menuToggleBtn');
    const mainMenuContent = document.getElementById('mainMenuContent');
    const submenuLinks = document.querySelectorAll('.dropdown-submenu > a');

    let desktopQuery;

    // Close all submenus
    function closeAllSubmenus() {
        document.querySelectorAll('.submenu-content').forEach(sub => {
            sub.classList.remove('show');
        });
    }

    // Update media query to match current screen (50% width)
    function updateMediaQuery() {
        const halfScreenWidth = window.screen.width / 2;
        if (desktopQuery) {
            desktopQuery.removeEventListener('change', handleDesktopChange);
        }

        desktopQuery = window.matchMedia(`(min-width: ${halfScreenWidth}px)`);
        desktopQuery.addEventListener('change', handleDesktopChange);
        handleDesktopChange(desktopQuery);
    }

    // Handle switching between mobile and desktop
    function handleDesktopChange(e) {
        if (e.matches) {
            mainMenuContent.classList.remove('show');
            closeAllSubmenus();
        }
    }

    // Initialize media query
    updateMediaQuery();

    // Recalculate on window resize
    window.addEventListener('resize', updateMediaQuery);

    // Toggle menu on mobile
    if (menuToggleBtn && mainMenuContent) {
        menuToggleBtn.addEventListener('click', function () {
            mainMenuContent.classList.toggle('show');
        });
    }

    // Toggle submenus on mobile
    submenuLinks.forEach(link => {
        link.addEventListener('click', function (event) {
            const submenu = link.nextElementSibling;

            if (submenu && submenu.classList.contains('submenu-content')) {
                if (!desktopQuery.matches) {
                    event.preventDefault();
                    submenu.classList.toggle('show');
                }
            }
        });
    });
});

