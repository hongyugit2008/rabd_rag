(function () {
  const MENU = [
    { href: '/chat', label: '会话窗口', key: 'chat', requiresAuth: true },
    { href: '/view/upload.html', label: '资料上传', key: 'upload', requiresAuth: true },
    { href: '/acl/manage', label: 'ACL管理', key: 'acl-manage', requiresAuth: true },
    { href: '/personal.html', label: '个人信息', key: 'personal', requiresAuth: true },
    { href: '/view/chroma_manage.html', label: 'Chroma 管理', key: 'chroma', requiresAuth: true },
    { href: '/view/user_manage.html', label: '用户管理', key: 'user-manage', requiresAuth: true },
    { href: '#logout', label: '退出系统', key: 'logout', action: 'logout', requiresAuth: true },
    { href: '/', label: '登录系统', key: 'login', guestOnly: true },
  ];

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function shouldShowItem(item, authenticated) {
    if (item.requiresAuth && !authenticated) return false;
    if (item.guestOnly && authenticated) return false;
    return true;
  }

  function renderItem(item, currentPage) {
    const isActive = item.key === currentPage ? ' active' : '';
    if (item.action === 'logout') {
      return `<a href="#logout" class="nav-link${isActive}" data-action="logout">${escapeHtml(item.label)}</a>`;
    }
    return `<a href="${item.href}" class="nav-link${isActive}">${escapeHtml(item.label)}</a>`;
  }

  function renderSidebar(options) {
    const { title = '工作区', subtitle = '快捷入口', currentPage = '', authenticated = true } = options || {};
    const items = MENU.filter((item) => shouldShowItem(item, authenticated));
    return `
      <div class="brand">${escapeHtml(title)}</div>
      <h4>${escapeHtml(subtitle)}</h4>
      <div class="nav">
        ${items.map((item) => renderItem(item, currentPage)).join('')}
      </div>
    `;
  }

  window.AppSidebar = { renderSidebar };
})();
