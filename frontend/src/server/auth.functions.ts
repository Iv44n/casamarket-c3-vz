import { redirect } from '@tanstack/react-router'
import { createServerFn } from '@tanstack/react-start'
import {
  deleteCookie,
  getCookie,
  setCookie
} from '@tanstack/react-start/server'
import { authenticateWithBackend, SESSION_COOKIE_NAME } from './backend.server'
import { loginRequestSchema } from './schemas'

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
  deleteCookie(SESSION_COOKIE_NAME, { path: '/' })
  throw redirect({ to: '/login' })
})

// Gate usado desde __root.tsx's beforeLoad -- corre siempre del lado del servidor
// (via RPC) sin importar si el beforeLoad se dispara en SSR o en una navegacion
// client-side, a diferencia de leer la cookie directo en el propio beforeLoad.
export const requireSession = createServerFn({ method: 'GET' }).handler(
  async () => {
    const token = getCookie(SESSION_COOKIE_NAME)
    if (!token) throw redirect({ to: '/login' })
  }
)
