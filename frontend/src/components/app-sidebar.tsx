import { Link, useRouterState } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import {
  ActivityIcon,
  BarChartHorizontalIcon,
  GaugeIcon,
  LogOutIcon,
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
  { to: '/usuarios' as const, label: 'Usuarios', icon: UsersIcon },
  { to: '/status' as const, label: 'Extraction status', icon: ActivityIcon }
] as const
export function AppSidebar() {
  const pathname = useRouterState({ select: state => state.location.pathname })
  const doLogout = useServerFn(logout)
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link to="/" />}>
              <span className="font-semibold">C3 Panel</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV_ITEMS.map(item => (
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
