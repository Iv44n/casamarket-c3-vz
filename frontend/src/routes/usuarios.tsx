import { createFileRoute } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import {
  EyeIcon,
  EyeOffIcon,
  ShieldAlertIcon,
  UserPlusIcon
} from 'lucide-react'
import { useCallback, useState } from 'react'
import { toast } from 'sonner'
import { Avatar, AvatarFallback } from '#/components/ui/avatar'
import { Badge } from '#/components/ui/badge'
import { Button } from '#/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '#/components/ui/card'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '#/components/ui/dialog'
import { Input } from '#/components/ui/input'
import { Label } from '#/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '#/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '#/components/ui/table'
import {
  createUser,
  getCurrentUser,
  getUsers,
  updateUserRole
} from '#/server/auth.functions'
import {
  type CurrentUser,
  USER_ROLE_LABEL,
  USER_ROLES,
  type UserRole
} from '#/server/schemas'

const ROLE_DESCRIPTION: Record<UserRole, string> = {
  admin: 'Todo el panel, más cuentas, configuración y catálogo.',
  user: 'Todo el panel.',
  incidencias: 'Solo la sección de incidencias manuales.'
}

function RoleSelect({
  id,
  value,
  onChange,
  disabled = false
}: {
  id?: string
  value: UserRole
  onChange: (role: UserRole) => void
  disabled?: boolean
}) {
  return (
    <Select
      value={value}
      onValueChange={next => {
        if (next) onChange(next as UserRole)
      }}
      disabled={disabled}
    >
      <SelectTrigger id={id} className="min-w-44 justify-between">
        <SelectValue>
          {(selected: UserRole) => USER_ROLE_LABEL[selected]}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {USER_ROLES.map(role => (
          <SelectItem key={role} value={role}>
            {USER_ROLE_LABEL[role]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export const Route = createFileRoute('/usuarios')({
  ssr: 'data-only',
  loader: async () => {
    const currentUser = await getCurrentUser()
    const users = currentUser.is_admin ? await getUsers() : []
    return { currentUser, users }
  },
  component: UsuariosPage
})

function UsuariosPage() {
  const { currentUser, users: initialUsers } = Route.useLoaderData()
  const doCreateUser = useServerFn(createUser)
  const doUpdateUserRole = useServerFn(updateUserRole)
  const fetchUsers = useServerFn(getUsers)
  const [users, setUsers] = useState(initialUsers)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('user')
  const [roleUpdating, setRoleUpdating] = useState<number | null>(null)
  const [showPassword, setShowPassword] = useState(false)
  const [pending, setPending] = useState(false)

  const refetchUsers = useCallback(async () => {
    try {
      setUsers(await fetchUsers())
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    }
  }, [fetchUsers])

  function resetForm() {
    setUsername('')
    setPassword('')
    setRole('user')
    setShowPassword(false)
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    try {
      const result = await doCreateUser({
        data: { username, password, role }
      })
      if (result.status === 'duplicate') {
        toast.error(`El usuario "${username}" ya existe.`)
        return
      }
      if (result.status === 'forbidden') {
        toast.error('No tenés permisos de administrador.')
        return
      }
      toast.success(`Usuario "${result.user.username}" creado.`)
      resetForm()
      setDialogOpen(false)
      await refetchUsers()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }

  async function handleRoleChange(user: CurrentUser, nextRole: UserRole) {
    if (nextRole === user.role) return
    setRoleUpdating(user.id)
    try {
      const result = await doUpdateUserRole({
        data: { userId: user.id, role: nextRole }
      })
      if (result.status === 'error') {
        toast.error(result.message)
        return
      }
      toast.success(
        `"${user.username}" ahora es ${USER_ROLE_LABEL[nextRole].toLowerCase()}.`
      )
      await refetchUsers()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setRoleUpdating(null)
    }
  }

  if (!currentUser.is_admin) {
    return (
      <div>
        <h1 className="text-2xl font-bold">Usuarios</h1>
        <Card className="mt-6">
          <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
            <ShieldAlertIcon className="size-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              Solo los administradores pueden ver esta sección.
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Usuarios</h1>
          <p className="mt-2 max-w-lg text-sm text-muted-foreground">
            Creá una cuenta para que alguien más pueda acceder al panel. No hay
            auto-registro -- las cuentas se crean solo desde acá.
          </p>
        </div>
        <Dialog
          open={dialogOpen}
          onOpenChange={open => {
            setDialogOpen(open)
            if (!open) resetForm()
          }}
        >
          <DialogTrigger render={<Button />}>
            <UserPlusIcon data-icon="inline-start" />
            Nuevo usuario
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Nuevo usuario</DialogTitle>
              <DialogDescription>
                La persona podrá iniciar sesión con este usuario y contraseña.
              </DialogDescription>
            </DialogHeader>
            <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
              <div className="flex flex-col gap-2">
                <Label htmlFor="new-username">Usuario</Label>
                <Input
                  id="new-username"
                  autoComplete="off"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="new-password">Contraseña</Label>
                <div className="relative">
                  <Input
                    id="new-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="pr-10"
                    required
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="absolute top-1/2 right-1 -translate-y-1/2"
                    onClick={() => setShowPassword(v => !v)}
                    aria-label={
                      showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'
                    }
                  >
                    {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                  </Button>
                </div>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="new-role">Rol</Label>
                <RoleSelect id="new-role" value={role} onChange={setRole} />
                <p className="text-xs text-muted-foreground">
                  {ROLE_DESCRIPTION[role]}
                </p>
              </div>
              <DialogFooter>
                <DialogClose
                  render={<Button type="button" variant="outline" />}
                >
                  Cancelar
                </DialogClose>
                <Button type="submit" disabled={pending}>
                  <UserPlusIcon data-icon="inline-start" />
                  {pending ? 'Creando...' : 'Crear usuario'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Cuentas</CardTitle>
          <CardDescription>{users.length} en total.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Usuario</TableHead>
                <TableHead>Rol</TableHead>
                <TableHead>Creado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map(user => (
                <TableRow key={user.id}>
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <Avatar size="sm">
                        <AvatarFallback>
                          {user.username.charAt(0).toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <span className="font-medium">{user.username}</span>
                      {user.username === currentUser.username && (
                        <span className="text-xs text-muted-foreground">
                          (vos)
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    {user.id === currentUser.id ? (
                      // El backend rechaza cambiar el rol propio (evita quedarse afuera).
                      <Badge variant="default">
                        {USER_ROLE_LABEL[user.role]}
                      </Badge>
                    ) : (
                      <RoleSelect
                        value={user.role}
                        onChange={next => handleRoleChange(user, next)}
                        disabled={roleUpdating === user.id}
                      />
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(user.created_at).toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
