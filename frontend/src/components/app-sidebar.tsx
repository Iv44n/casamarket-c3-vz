import { Link, useRouterState } from '@tanstack/react-router'
import { ActivityIcon, BarChartHorizontalIcon, TableIcon } from 'lucide-react'
import { ModeToggle } from '#/components/mode-toggle'
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

const NAV_ITEMS = [
  { to: '/reports' as const, label: 'Reportes', icon: TableIcon },
  {
    to: '/atenciones' as const,
    label: 'Atenciones',
    icon: BarChartHorizontalIcon
  },
  { to: '/status' as const, label: 'Extraction status', icon: ActivityIcon }
] as const
export function AppSidebar() {
  const pathname = useRouterState({ select: state => state.location.pathname })
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
        <ModeToggle />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
