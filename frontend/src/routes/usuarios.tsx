import { createFileRoute } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import {
  EyeIcon,
  EyeOffIcon,
  PencilIcon,
  SaveIcon,
  ShieldAlertIcon,
  Trash2Icon,
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
  Tooltip,
  TooltipContent,
  TooltipTrigger
} from '#/components/ui/tooltip'
import {
  createUser,
  deleteUser,
  getCurrentUser,
  getUsers,
  updateUser
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
      <SelectTrigger id={id} className="w-full justify-between">
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

function PasswordInput({
  id,
  value,
  onChange,
  required = false,
  placeholder
}: {
  id: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  placeholder?: string
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <Input
        id={id}
        type={show ? 'text' : 'password'}
        autoComplete="new-password"
        value={value}
        onChange={e => onChange(e.target.value)}
        className="pr-10"
        placeholder={placeholder}
        required={required}
      />
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="absolute top-1/2 right-1 -translate-y-1/2"
        onClick={() => setShow(v => !v)}
        aria-label={show ? 'Ocultar contraseña' : 'Mostrar contraseña'}
      >
        {show ? <EyeOffIcon /> : <EyeIcon />}
      </Button>
    </div>
  )
}

// Edicion de una cuenta. Solo se manda lo que cambio. En la propia cuenta solo la contraseña:
// el backend rechaza cambiarse el rol (quedaria afuera) o el usuario (invalidaria su propio
// token a mitad de sesion). Se monta de nuevo en cada apertura (`key` en el caller), asi el form
// arranca siempre con los datos actuales de esa cuenta.
function EditUserDialog({
  user,
  isSelf,
  open,
  onOpenChange,
  onSaved
}: {
  user: CurrentUser
  isSelf: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => Promise<void>
}) {
  const doUpdate = useServerFn(updateUser)
  const [username, setUsername] = useState(user.username)
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>(user.role)
  const [pending, setPending] = useState(false)
  const renaming = username.trim().toLowerCase() !== user.username

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const changes: { username?: string; password?: string; role?: UserRole } =
      {}
    if (!isSelf && renaming) changes.username = username.trim()
    if (password) changes.password = password
    if (!isSelf && role !== user.role) changes.role = role
    if (Object.keys(changes).length === 0) {
      toast.info('No hay cambios para guardar.')
      return
    }
    setPending(true)
    try {
      const result = await doUpdate({ data: { userId: user.id, ...changes } })
      if (result.status === 'error') {
        toast.error(result.message)
        return
      }
      toast.success(`Cuenta "${result.user.username}" actualizada.`)
      onOpenChange(false)
      await onSaved()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Editar usuario</DialogTitle>
          <DialogDescription>
            {isSelf
              ? 'En tu propia cuenta solo podés cambiar la contraseña.'
              : 'Dejá la contraseña vacía para no cambiarla.'}
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-2">
            <Label htmlFor="edit-username">Usuario</Label>
            <Input
              id="edit-username"
              autoComplete="off"
              value={username}
              onChange={e => setUsername(e.target.value)}
              disabled={isSelf}
              maxLength={120}
              required
            />
            {renaming && (
              <p className="text-xs text-muted-foreground">
                Al cambiar el usuario, esa persona tendrá que volver a iniciar
                sesión con el nombre nuevo.
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="edit-password">Nueva contraseña</Label>
            <PasswordInput
              id="edit-password"
              value={password}
              onChange={setPassword}
              placeholder="Sin cambios"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="edit-role">Rol</Label>
            <RoleSelect
              id="edit-role"
              value={role}
              onChange={setRole}
              disabled={isSelf}
            />
            <p className="text-xs text-muted-foreground">
              {ROLE_DESCRIPTION[role]}
            </p>
          </div>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" />}>
              Cancelar
            </DialogClose>
            <Button type="submit" disabled={pending}>
              <SaveIcon data-icon="inline-start" />
              {pending ? 'Guardando...' : 'Guardar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
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
  const doDeleteUser = useServerFn(deleteUser)
  const fetchUsers = useServerFn(getUsers)
  const [users, setUsers] = useState(initialUsers)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('user')
  const [pending, setPending] = useState(false)
  const [editing, setEditing] = useState<CurrentUser | undefined>()
  const [editOpen, setEditOpen] = useState(false)
  const [editKey, setEditKey] = useState(0)
  const [deleting, setDeleting] = useState<CurrentUser | undefined>()
  const [deletePending, setDeletePending] = useState(false)

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
  }

  function openEdit(user: CurrentUser) {
    setEditing(user)
    setEditKey(key => key + 1)
    setEditOpen(true)
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

  async function handleConfirmDelete() {
    if (!deleting) return
    setDeletePending(true)
    try {
      const result = await doDeleteUser({ data: { userId: deleting.id } })
      if (result.status === 'error') {
        toast.error(result.message)
        return
      }
      toast.success(`Cuenta "${deleting.username}" eliminada.`)
      setDeleting(undefined)
      await refetchUsers()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setDeletePending(false)
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
            Creá, editá o eliminá las cuentas que acceden al panel. No hay
            auto-registro -- las cuentas se gestionan solo desde acá.
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
                  maxLength={120}
                  required
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="new-password">Contraseña</Label>
                <PasswordInput
                  id="new-password"
                  value={password}
                  onChange={setPassword}
                  required
                />
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
                <TableHead className="text-right">
                  <span className="sr-only">Acciones</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map(user => {
                const isSelf = user.id === currentUser.id
                return (
                  <TableRow key={user.id}>
                    <TableCell>
                      <div className="flex items-center gap-2.5">
                        <Avatar size="sm">
                          <AvatarFallback>
                            {user.username.charAt(0).toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                        <span className="font-medium">{user.username}</span>
                        {isSelf && (
                          <span className="text-xs text-muted-foreground">
                            (vos)
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          user.role === 'admin' ? 'default' : 'secondary'
                        }
                      >
                        {USER_ROLE_LABEL[user.role]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(user.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Tooltip>
                          <TooltipTrigger
                            render={
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                aria-label={`Editar ${user.username}`}
                                onClick={() => openEdit(user)}
                              />
                            }
                          >
                            <PencilIcon />
                          </TooltipTrigger>
                          <TooltipContent>Editar</TooltipContent>
                        </Tooltip>
                        {!isSelf && (
                          // Eliminarse a uno mismo lo rechaza el backend (quedaria afuera).
                          <Tooltip>
                            <TooltipTrigger
                              render={
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  aria-label={`Eliminar ${user.username}`}
                                  onClick={() => setDeleting(user)}
                                />
                              }
                            >
                              <Trash2Icon />
                            </TooltipTrigger>
                            <TooltipContent>Eliminar</TooltipContent>
                          </Tooltip>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {editing && (
        <EditUserDialog
          key={editKey}
          user={editing}
          isSelf={editing.id === currentUser.id}
          open={editOpen}
          onOpenChange={setEditOpen}
          onSaved={refetchUsers}
        />
      )}

      <Dialog
        open={deleting !== undefined}
        onOpenChange={open => {
          if (!open) setDeleting(undefined)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              ¿Eliminar la cuenta "{deleting?.username}"?
            </DialogTitle>
            <DialogDescription>
              La persona pierde el acceso de inmediato y no se puede deshacer.
              Las incidencias que haya registrado se conservan.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" />}>
              Cancelar
            </DialogClose>
            <Button
              variant="destructive"
              onClick={handleConfirmDelete}
              disabled={deletePending}
            >
              <Trash2Icon data-icon="inline-start" />
              {deletePending ? 'Eliminando...' : 'Eliminar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
