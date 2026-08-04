const workspaceItems = [
  { label: '审核概览', to: '/home', icon: 'apps-o' },
  { label: '证照查询', to: '/query', icon: 'search' },
  { label: '证照审核', to: '/review', icon: 'records-o', adminOnly: true },
  { label: '一致性校验', to: '/tobacco/reports', icon: 'balance-list' },
  { label: '效期看板', to: '/dashboard', icon: 'bar-chart-o' },
]

const managementItems = [
  { label: '系统配置', to: '/admin', icon: 'setting-o', adminOnly: true },
]

function isRouteActive(currentPath, targetPath) {
  return currentPath === targetPath || currentPath.startsWith(`${targetPath}/`)
}

function visibleItems(items, isAdmin, currentPath) {
  return items
    .filter(item => !item.adminOnly || isAdmin)
    .map(item => ({ ...item, active: isRouteActive(currentPath, item.to) }))
}

export function buildDesktopNavigation({ isAdmin, currentPath }) {
  const groups = [
    { label: '工作空间', items: visibleItems(workspaceItems, isAdmin, currentPath) },
  ]
  const management = visibleItems(managementItems, isAdmin, currentPath)
  if (management.length) groups.push({ label: '管理', items: management })
  return groups
}

export function buildMobileNavigation({ isAdmin, currentPath }) {
  const items = isAdmin
    ? [
        { label: '首页', to: '/home', icon: 'home-o' },
        { label: '审核', to: '/review', icon: 'records-o' },
        { label: '看板', to: '/dashboard', icon: 'bar-chart-o' },
        { label: '我的', to: '/profile', icon: 'contact-o' },
      ]
    : [
        { label: '首页', to: '/home', icon: 'home-o' },
        { label: '查询', to: '/query', icon: 'search' },
        { label: '看板', to: '/dashboard', icon: 'bar-chart-o' },
        { label: '我的', to: '/profile', icon: 'contact-o' },
      ]
  return items.map(item => ({ ...item, active: isRouteActive(currentPath, item.to) }))
}
