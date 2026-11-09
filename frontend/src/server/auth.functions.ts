import { redirect } from '@tanstack/react-router'
import { createServerFn } from '@tanstack/react-start'
import {
  deleteCookie,
  getCookie,
  setCookie
} from '@tanstack/react-start/server'
import {
  authenticateWithBackend,
  createUserOnBackend,
  deleteUserOnBackend,
  fetchCurrentUser,
  fetchSessionUser,
  fetchUsers,
  forgetSessionUser,
  SESSION_COOKIE_NAME,
  updateUserOnBackend
} from './backend.server'
import {
  createUserRequestSchema,
  deleteUserRequestSchema,
  loginRequestSchema,
  updateUserRequestSchema
} from './schemas'

const SESSION_COOKIE_MAX_AGE_SECONDS = 14 * 24 * 60 * 60

export const login = createServerFn({ method: 'POST' })
  .validator(loginRequestSchema)
  .handler(async ({ data }) => {
    const token = await authenticateWithBackend(data.username, data.password)
    if (token === null) {
      throw new Error('Usuario o contraseña incorrectos')
    }
    setCookie(SESSION_COOKIE_NAME, token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: SESSION_COOKIE_MAX_AGE_SECONDS,
      path: '/'
    })
  })

export const logout = createServerFn({ method: 'POST' }).handler(async () => {
  forgetSessionUser(getCookie(SESSION_COOKIE_NAME))
  deleteCookie(SESSION_COOKIE_NAME, { path: '/' })
  throw redirect({ to: '/login' })
})

// Gate usado desde __root.tsx's beforeLoad -- corre siempre del lado del servidor
// (via RPC) sin importar si el beforeLoad se dispara en SSR o en una navegacion
// client-side, a diferencia de leer la cookie directo en el propio beforeLoad.
// Devuelve el usuario de la sesion (con su rol, para decidir que secciones se ven) --
// cacheado por token en backend.server.ts's fetchSessionUser, asi que no cuesta un
// /auth/me por navegacion.
export const requireSession = createServerFn({ method: 'GET' }).handler(
  async () => fetchSessionUser()
)

export const getCurrentUser = createServerFn({ method: 'GET' }).handler(
  async () => fetchCurrentUser()
)

export const createUser = createServerFn({ method: 'POST' })
  .validator(createUserRequestSchema)
  .handler(async ({ data }) =>
    createUserOnBackend(data.username, data.password, data.role)
  )

export const updateUser = createServerFn({ method: 'POST' })
  .validator(updateUserRequestSchema)
  .handler(async ({ data: { userId, ...changes } }) =>
    updateUserOnBackend(userId, changes)
  )

export const deleteUser = createServerFn({ method: 'POST' })
  .validator(deleteUserRequestSchema)
  .handler(async ({ data }) => deleteUserOnBackend(data.userId))

export const getUsers = createServerFn({ method: 'GET' }).handler(async () =>
  fetchUsers()
)
