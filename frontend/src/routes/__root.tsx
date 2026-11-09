import { TanStackDevtools } from '@tanstack/react-devtools'
import {
  createRootRoute,
  HeadContent,
  redirect,
  Scripts,
  useRouterState
} from '@tanstack/react-router'
import { TanStackRouterDevtoolsPanel } from '@tanstack/react-router-devtools'
import { AppSidebar } from '#/components/app-sidebar'
import { AutoRefreshProvider } from '#/components/auto-refresh-provider'
import { BenchmarkScheduleProvider } from '#/components/benchmark-schedule-provider'
import { ThemeProvider } from '#/components/theme-provider'
import Toaster from '#/components/toaster'
import { Separator } from '#/components/ui/separator'
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger
} from '#/components/ui/sidebar'
import { TooltipProvider } from '#/components/ui/tooltip'
import { useSessionUser } from '#/hooks/use-session-user'
import { canAccessPath, hasFullAccess, homePathFor } from '#/lib/access'
import { cn } from '#/lib/utils'
import { requireSession } from '#/server/auth.functions'
import type { SessionUser } from '#/server/schemas'
import appCss from '../styles.css?url'
export const Route = createRootRoute({
  beforeLoad: async ({
    location
  }): Promise<{ sessionUser: SessionUser | null }> => {
    if (location.pathname === '/login') return { sessionUser: null }
    const sessionUser = await requireSession()
    // El rol "incidencias" solo ve /incidencias-manuales: cualquier otra URL (incluida "/")
    // lo manda ahi. Ver lib/access.ts -- el backend igual le responde 403 a todo lo demas.
    if (!canAccessPath(sessionUser.role, location.pathname)) {
      throw redirect({ to: homePathFor(sessionUser.role) })
    }
    return { sessionUser }
  },
  head: () => ({
    meta: [
      {
        charSet: 'utf-8'
      },
      {
        name: 'viewport',
        content: 'width=device-width, initial-scale=1'
      },
      {
        title: 'C3 Panel'
      }
    ],
    links: [
      {
        rel: 'stylesheet',
        href: appCss
      }
    ]
  }),
  shellComponent: RootDocument
})
function RootDocument({ children }: { children: React.ReactNode }) {
  const pathname = useRouterState({ select: state => state.location.pathname })
  const sessionUser = useSessionUser()
  // Los timers (POST /extraction/refresh, corridas de benchmarks) arrancan solo cuando se sabe
  // que la cuenta puede usarlos -- al rol "incidencias" le responderian 403 cada 5 minutos.
  const timersEnabled = sessionUser !== null && hasFullAccess(sessionUser.role)
  const isWallboard = pathname === '/atenciones'
  const isFullWidth = pathname === '/benchmarks'
  const isAuthPage = pathname === '/login'
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <HeadContent />
      </head>
      <body>
        <ThemeProvider defaultTheme="system" storageKey="theme">
          {isAuthPage ? (
            <>
              <TooltipProvider>{children}</TooltipProvider>
              <Toaster />
            </>
          ) : (
            <AutoRefreshProvider enabled={false}>
              <BenchmarkScheduleProvider enabled={timersEnabled}>
                <TooltipProvider>
                  <SidebarProvider>
                    <AppSidebar />
                    <SidebarInset className="min-w-0">
                      <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
                        <SidebarTrigger />
                        <Separator orientation="vertical" className="h-4" />
                      </header>
                      <div className="flex min-h-0 flex-1 flex-col">
                        <div
                          className={cn(
                            'flex flex-1 flex-col',
                            isWallboard
                              ? 'min-h-[calc(100dvh-3.5rem)] px-6 py-4'
                              : isFullWidth
                                ? 'w-full px-6 py-8'
                                : 'mx-auto w-full max-w-5xl px-4 py-8'
                          )}
                        >
                          {children}
                        </div>
                      </div>
                    </SidebarInset>
                  </SidebarProvider>
                </TooltipProvider>
                <Toaster />
              </BenchmarkScheduleProvider>
            </AutoRefreshProvider>
          )}
        </ThemeProvider>
        <TanStackDevtools
          config={{
            position: 'bottom-right'
          }}
          plugins={[
            {
              name: 'Tanstack Router',
              render: <TanStackRouterDevtoolsPanel />
            }
          ]}
        />
        <Scripts />
      </body>
    </html>
  )
}
