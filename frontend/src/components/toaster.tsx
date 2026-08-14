import { Toaster as SonnerToaster } from 'sonner'
import { useTheme } from '#/components/theme-provider'
export default function Toaster() {
  const { theme } = useTheme()
  return <SonnerToaster theme={theme} richColors closeButton />
}
