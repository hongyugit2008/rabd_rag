(function () {
  function toggleWorkspace() {
    const ws = document.getElementById('workspace');
    const main = document.getElementById('main');
    if (!ws) return;
    ws.classList.toggle('collapsed');
    if (main) main.classList.toggle('expanded');
    localStorage.setItem('workspace_collapsed', ws.classList.contains('collapsed') ? '1' : '0');
  }

  function restoreWorkspaceState() {
    const ws = document.getElementById('workspace');
    const main = document.getElementById('main');
    if (!ws) return;
    if (localStorage.getItem('workspace_collapsed') === '1') {
      ws.classList.add('collapsed');
      if (main) main.classList.add('expanded');
    }
  }

  function mountSidebar(currentPage, options) {
    const slot = document.getElementById('sidebarSlot');
    if (!slot || !window.AppSidebar) return;
    slot.innerHTML = window.AppSidebar.renderSidebar({ currentPage, ...(options || {}) });
    const logoutBtn = document.querySelector('[data-action="logout"]');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', function (event) {
        event.preventDefault();
        if (typeof window.logout === 'function') window.logout();
      });
    }
  }

  window.AppShell = { toggleWorkspace, restoreWorkspaceState, mountSidebar };
})();
