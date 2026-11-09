import { useRouterState } from '@tanstack/react-router'
import type { SessionUser } from '#/server/schemas'

// Usuario de la sesion que __root.tsx's beforeLoad deja en el contexto del router. El shell (y
// el sidebar) tambien se renderizan en SSR, antes de que ese beforeLoad haya corrido (las rutas
// son client-side, ver start.ts) -- por eso se lee del estado del router con fallback a null en
// vez de Route.useRouteContext(), que asume que el contexto ya existe.
export function useSessionUser(): SessionUser | null {
  return useRouterState({
    select: state =>
      (state.matches[0]?.context as { sessionUser?: SessionUser | null })
        ?.sessionUser ?? null
  })
}
