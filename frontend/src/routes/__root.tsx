import { TanStackDevtools } from '@tanstack/react-devtools'
import { createRootRoute, HeadContent, Scripts } from '@tanstack/react-router'
import { TanStackRouterDevtoolsPanel } from '@tanstack/react-router-devtools'
import { AutoRefreshProvider } from '#/components/auto-refresh-provider'
import { SiteHeader } from '#/components/site-header'
import { ThemeProvider } from '#/components/theme-provider'
import Toaster from '#/components/toaster'
import { TooltipProvider } from '#/components/ui/tooltip'
import appCss from '../styles.css?url'
export const Route = createRootRoute({
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
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <HeadContent />
      </head>
      <body>
        <ThemeProvider defaultTheme="system" storageKey="theme">
          <AutoRefreshProvider>
            <TooltipProvider>
              <SiteHeader />
              <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
            </TooltipProvider>
            <Toaster />
          </AutoRefreshProvider>
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
