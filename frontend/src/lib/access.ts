import type { UserRole } from '#/server/schemas'

// Unica fuente de que rol ve que seccion en el frontend -- la usan __root.tsx (redirect) y
// app-sidebar.tsx (que items mostrar). El bloqueo real vive en el backend
// (auth/dependencies.py: require_full_access responde 403 al rol "incidencias"); esto solo evita
// mostrarle pantallas que van a fallar.

export const MANUAL_INCIDENTS_PATH = '/incidencias-manuales'

// null = sin restriccion (todo el panel).
const ALLOWED_PATHS: Record<UserRole, readonly string[] | null> = {
  admin: null,
  user: null,
  incidencias: [MANUAL_INCIDENTS_PATH]
}

export function canAccessPath(role: UserRole, pathname: string): boolean {
  const allowed = ALLOWED_PATHS[role]
  if (allowed === null) return true
  return allowed.some(
    path => pathname === path || pathname.startsWith(`${path}/`)
  )
}

export function homePathFor(
  role: UserRole
): '/' | typeof MANUAL_INCIDENTS_PATH {
  return role === 'incidencias' ? MANUAL_INCIDENTS_PATH : '/'
}

// Los timers de __root.tsx (auto-refresh de C3, benchmarks programados) solo tienen sentido
// para quien puede usar esos endpoints.
export function hasFullAccess(role: UserRole): boolean {
  return ALLOWED_PATHS[role] === null
}
