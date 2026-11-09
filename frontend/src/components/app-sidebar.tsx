import { Link, useRouterState } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import {
  ActivityIcon,
  BarChartHorizontalIcon,
  GaugeIcon,
  LogOutIcon,
  NotebookPenIcon,
  TableIcon,
  TrendingUpIcon,
  UsersIcon
} from 'lucide-react'
import { ModeToggle } from '#/components/mode-toggle'
import { Button } from '#/components/ui/button'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail
} from '#/components/ui/sidebar'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger
} from '#/components/ui/tooltip'
import { useSessionUser } from '#/hooks/use-session-user'
import { canAccessPath, homePathFor } from '#/lib/access'
import { logout } from '#/server/auth.functions'

const NAV_ITEMS = [
  { to: '/reports' as const, label: 'Reportes', icon: TableIcon },
  {
    to: '/atenciones' as const,
    label: 'Atenciones',
    icon: BarChartHorizontalIcon
  },
  {
    to: '/tendencias-historicas' as const,
    label: 'Tendencias históricas',
    icon: TrendingUpIcon
  },
  { to: '/benchmarks' as const, label: 'Benchmarks', icon: GaugeIcon },
  {
    to: '/incidencias-manuales' as const,
    label: 'Incidencias manuales',
    icon: NotebookPenIcon
  },
  { to: '/usuarios' as const, label: 'Usuarios', icon: UsersIcon },
  { to: '/status' as const, label: 'Extraction status', icon: ActivityIcon }
] as const
export function AppSidebar() {
  const pathname = useRouterState({ select: state => state.location.pathname })
  const doLogout = useServerFn(logout)
  const sessionUser = useSessionUser()
  // Sin sesion resuelta todavia (primer render, SSR) no se muestra ningun item: mejor un
  // instante vacio que mostrarle al rol "incidencias" secciones a las que no puede entrar.
  const navItems = sessionUser
    ? NAV_ITEMS.filter(item => canAccessPath(sessionUser.role, item.to))
    : []
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              render={
                <Link to={sessionUser ? homePathFor(sessionUser.role) : '/'} />
              }
            >
              <span className="font-semibold">C3 Panel</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map(item => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton
                    render={<Link to={item.to} />}
                    isActive={
                      pathname === item.to || pathname.startsWith(`${item.to}/`)
                    }
                    tooltip={item.label}
                  >
                    <item.icon />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <div className="flex items-center gap-1">
          <ModeToggle />
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Cerrar sesion"
                  onClick={() => doLogout()}
                />
              }
            >
              <LogOutIcon />
            </TooltipTrigger>
            <TooltipContent>Cerrar sesion</TooltipContent>
          </Tooltip>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
