# Plan: Incidencias manuales + rol "Solo incidencias"

> **Estado (2026-11-09): implementado** en la rama `incidencias-manuales` (sin commitear). Los
> supuestos de la sección "Supuestos a confirmar" se aplicaron tal cual. Diferencias menores con
> este plan: `manual_incident.hora` es `TEXT NOT NULL DEFAULT ''` (no nullable), y el CLI de shadcn
> instaló por error un paquete npm `cn` (se removió; ver `frontend/CLAUDE.md`). Verificado con
> pytest (517 tests), typecheck, biome y un recorrido en Chrome headless contra un backend falso.

## Contexto

Hoy las incidencias del panel salen **solo de C3**: son los campos `Origen de incidencia`,
`Tipo de incidencia`, `Ámbito de incidencia`, `Resultado de la atención` y
`Descripción de la incidencia` de las atenciones (`attention`, `outboundattention`,
`calloutgoing`), y se ven en `/atenciones?view=incidencias` (`lib/incident-analytics.ts`,
`components/incident-hierarchy.tsx`).

Se pide:

1. Una **sección nueva** para **registrar incidencias desde cero, a mano**: incidencias que no
   pasan por C3.
2. Un **rol nuevo** para que ciertos usuarios vean **solo esa sección** y nada de lo que ya existe.

Decisiones tomadas con el usuario (2026-11-09):

| Tema | Decisión |
|---|---|
| Qué es "llenar a mano" | Registrar incidencias nuevas desde cero (tabla propia en Turso) |
| Permisos del rol nuevo | Crear, ver, editar y borrar **todas** las incidencias manuales (no solo las suyas) |
| Integración con `/atenciones` | **No**: las manuales quedan solo en la sección nueva |
| Origen/Tipo/Ámbito/Resultado | Desplegables con los valores de C3 **y** catálogo editable por admins |

Estado actual del control de acceso (por qué el rol necesita cambios en el backend, no solo en el
menú): el único permiso que existe es `users.is_admin`, y solo lo exigen `GET/POST /auth/users` y
`PUT /benchmarks/settings`. **Cualquier usuario logueado puede llamar a todos los demás endpoints**
(`/data/*`, `/extraction/*`, `/benchmarks/*`). Además, las server functions de TanStack Start son
endpoints RPC que el navegador puede invocar directamente. Por eso ocultar ítems del sidebar no
alcanza: el bloqueo real tiene que vivir en el backend.

Datos reales de la taxonomía (consulta de solo lectura a Turso, 2026-11-09):

- Las 4 categorías son **independientes**. Por ejemplo, el tipo `CONSULTAS` aparece con 17 orígenes
  y 86 ámbitos distintos. Entonces el catálogo son **4 listas planas**, no desplegables en cascada.
- Valores distintos: ~19 orígenes, 14 tipos, ~90 ámbitos y 10 resultados. Con ~90 ámbitos hace
  falta un **selector con búsqueda** (combobox), no un `<select>` simple.
- Hay valores basura que no se deben importar al catálogo: `NULL`, `''`, `'-'`, `'N.A'`.
  `NO APLICA` sí es una opción real de C3: se importa y el admin puede desactivarla.

## Diseño

### 1. Roles en `users` (backend, `app/auth/`)

- Columna nueva `users.role TEXT` con 3 valores: `admin`, `user` y `incidencias`. La UI muestra
  "Administrador", "Usuario" y "Solo incidencias".
- **Migración aditiva**, con el mismo patrón que `_migrate_*` en `extraction/store.py`: si
  `PRAGMA table_info(users)` no tiene `role`, se corre `ALTER TABLE users ADD COLUMN role TEXT` y
  después `UPDATE users SET role = CASE WHEN is_admin = 1 THEN 'admin' ELSE 'user' END WHERE role IS NULL`.
  Se dispara una sola vez, lazy, dentro de `_init_schema`.
- `is_admin` **se sigue escribiendo** en sincronía (`is_admin = role == 'admin'`). Es `NOT NULL`, y
  así un rollback a código viejo sigue funcionando. La fuente de verdad pasa a ser `role`.
- `UserRecord` gana `role`; `is_admin` queda derivado. `create_user(..., role)`. Funciones nuevas:
  `get_user_by_id`, `update_user_role` y `count_admins`.
- El JWT agrega el claim `role`. Al decodificar un token viejo sin `role`, se deriva de `is_admin`.

### 2. Verificar el rol contra la DB, con caché corta (`app/auth/dependencies.py`)

Problema: si un admin cambia a alguien de `user` a `incidencias`, su token viejo dice `user`
durante 14 días.

- Dependencias nuevas: `require_full_access` (roles `admin` y `user`) y
  `require_incidents_access` (`admin`, `user` e `incidencias`). Las dos resuelven el rol **actual**
  con una caché en memoria por `user_id` con **TTL de 60 s** (dict + lock, misma arquitectura de
  un solo proceso que `extraction/state.py`). Si no hay entrada en la caché, se hace una lectura a
  Turso.
- Si la cuenta ya no existe, la respuesta es `401`. Esto también achica el "Known remaining gap"
  documentado en `backend/CLAUDE.md`: una cuenta borrada deja de funcionar en ≤60 s.
- `PATCH /auth/users/{id}` **invalida** la entrada de la caché de ese usuario, así que el cambio de
  rol aplica de inmediato.
- `runs.router`, `data.router` y `benchmarks.router` pasan de `Depends(get_current_user)` a
  `Depends(require_full_access)`. Es un cambio de una línea en cada `APIRouter(...)`; ningún handler
  cambia.
- `require_admin` queda como está (ya verifica contra la DB).

Costo: como mucho una lectura a Turso por usuario por minuto (~0,4 s cuando la caché no tiene el
dato).

### 3. Endpoints de usuarios (`app/routers/auth.py`)

- `UserPublic` gana `role` y mantiene `is_admin` derivado para no romper nada.
- `CreateUserRequest.role: Literal['admin','user','incidencias'] = 'user'` reemplaza a `is_admin`.
- Endpoint nuevo `PATCH /auth/users/{user_id}` con cuerpo `{role}`, solo para admins:
  - `400` si un admin intenta cambiar su propio rol (evita quedarse afuera).
  - `409` si el cambio dejaría el sistema sin ningún admin.
  - `404` si el usuario no existe.
- `/auth/login` incluye `role` en el token. `/auth/me` devuelve `role`.

### 4. Dominio nuevo `app/incidents/` (backend)

`incidents/store.py` tiene su propio `get_connection()` con schema lazy, igual que
`auth/store.py` y `benchmarks/settings.py`: misma base Turso, dominio separado.

```sql
CREATE TABLE IF NOT EXISTS manual_incident (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha        TEXT NOT NULL,              -- YYYY-MM-DD (America/Lima)
    hora         TEXT,                        -- HH:MM, opcional
    cliente      TEXT NOT NULL DEFAULT '',    -- nombre / empresa
    telefono     TEXT NOT NULL DEFAULT '',
    agente       TEXT NOT NULL DEFAULT '',    -- quien atendio
    origen       TEXT NOT NULL,
    tipo         TEXT NOT NULL,
    ambito       TEXT NOT NULL,
    resultado    TEXT NOT NULL DEFAULT '',
    descripcion  TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_by   TEXT,
    updated_at   TEXT,
    deleted_by   TEXT,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_manual_incident_fecha ON manual_incident(fecha);

CREATE TABLE IF NOT EXISTS incident_catalog_option (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL CHECK (category IN ('origen','tipo','ambito','resultado')),
    value       TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    source      TEXT NOT NULL,                -- 'c3' | 'manual'
    created_at  TEXT NOT NULL,
    UNIQUE (category, value)
);
```

- **Valores guardados como texto** en la incidencia, no como FK. Así, desactivar una opción del
  catálogo no altera el historial. Al editar una incidencia que tiene un valor ya desactivado, ese
  valor sigue siendo válido para esa incidencia.
- **Borrado lógico** (`deleted_at`/`deleted_by`): como cualquier usuario del rol puede borrar
  incidencias de otros, así queda recuperable desde la DB. Los listados excluyen las borradas.
- **Validación en el servidor**: origen, tipo y ámbito son obligatorios y deben ser opciones
  activas del catálogo (o el valor que la incidencia ya tenía). Resultado es opcional, con la misma
  regla. `descripcion` es obligatoria. `fecha` debe ser una fecha ISO válida.
- **Catálogo sin renombrar**: solo se puede agregar y activar/desactivar. Renombrar obligaría a
  decidir si se reescribe el historial; queda fuera de este alcance.
- **Importar desde C3**: función nueva en `extraction/store.py` (dueño de esas tablas),
  `distinct_incident_values(conn)`. Hace `json_extract` de los 4 campos sobre `attention`,
  `outboundattention` y `calloutgoing`, y excluye `NULL`, `''`, `'-'` y `'N.A'` sin distinguir
  mayúsculas. `incidents/store.py` inserta con `INSERT OR IGNORE`: es idempotente y **nunca
  reactiva** una opción que un admin desactivó. Devuelve cuántas opciones se agregaron.

Router `app/routers/incidents.py`, con prefijo `/incidents`:

| Método y ruta | Acceso | Qué hace |
|---|---|---|
| `GET /incidents?date_from&date_to` | incidencias+ | Lista por rango de fechas, `fecha DESC, hora DESC`. Tope de 2000 filas con flag `truncated` |
| `POST /incidents` | incidencias+ | Crear (`created_by` = usuario del token) |
| `PUT /incidents/{id}` | incidencias+ | Editar (`updated_by`/`updated_at`) |
| `DELETE /incidents/{id}` | incidencias+ | Borrado lógico |
| `GET /incidents/catalog` | incidencias+ | Todas las opciones con su flag `active` |
| `POST /incidents/catalog` | admin | Agregar `{category, value}` (`409` si ya existe) |
| `PATCH /incidents/catalog/{id}` | admin | `{active}` |
| `POST /incidents/catalog/import-c3` | admin | Importar valores de C3 → `{added}` |

"incidencias+" significa los roles `admin`, `user` e `incidencias`.

Sin paginación en el servidor para el listado, a propósito: la carga manual genera decenas o pocos
cientos de filas por día, no los miles de las atenciones de C3. Si eso cambia, se migra al patrón
`/page` que ya usan las atenciones.

### 5. Sesión y control de acceso en el frontend

- `requireSession` (en `server/auth.functions.ts`) hoy solo verifica que exista la cookie. Pasa a
  **devolver el usuario de sesión** `{ id, username, role }` usando `/auth/me`, con una caché por
  token de 60 s en `backend.server.ts` (mismo patrón que `_reportRowsCache`). El `beforeLoad` raíz
  corre en cada navegación, y sin caché agregaría un viaje a Turso a cada una.
- `lib/access.ts` (nuevo) es la **única fuente** de qué rol ve qué:
  - `canAccessPath(role, pathname)`: `incidencias` solo puede entrar a `/incidencias-manuales`.
  - `homePathFor(role)`: `/incidencias-manuales` para ese rol; `/` para el resto.
- `__root.tsx` `beforeLoad`: pone `sessionUser` en el contexto del router y, si
  `canAccessPath(...)` da falso, redirige a `homePathFor(role)`. Un usuario restringido que escribe
  `/atenciones` en la URL termina en su sección.
- **`AutoRefreshProvider` y `BenchmarkScheduleProvider` no programan nada** si el rol no tiene
  acceso completo, ni mientras el rol todavía no se conoce. Reciben una prop `enabled` y siguen
  proveyendo el contexto, para no remontar el árbol. Sin esto, la pestaña de un usuario restringido
  dispararía `POST /extraction/refresh` cada 5 minutos, recibiría `403` y mostraría toasts de error.
- `app-sidebar.tsx`: filtra `NAV_ITEMS` con `canAccessPath`. Ítem nuevo
  **"Incidencias manuales"** (icono `NotebookPenIcon`), visible para los 3 roles.
- El enforcement real sigue en el backend (sección 2). Esto es solo para que la experiencia no
  muestre pantallas rotas.

### 6. Página `/incidencias-manuales` (frontend)

- Encabezado, filtro de fechas `DateRangeFilter` (por defecto **hoy**, nunca "todas", igual que el
  resto de la app; `search` validado con zod y `.default(todayIsoDate)`) y botón
  **"Nueva incidencia"**.
- Pestañas:
  - **Registro**: tabla con fecha/hora, cliente, teléfono, origen, tipo, ámbito, resultado,
    descripción y "registrado por". Acciones por fila: editar (abre el mismo diálogo) y borrar (con
    confirmación). Paginación del lado del cliente sobre el rango ya cargado.
  - **Resumen**: reutiliza `IncidentHierarchy` tal cual. Las incidencias manuales se mapean a
    `IncidentRecord`, con selector de categoría como en `/atenciones`. Así el rol restringido tiene
    la misma visualización en escalera.
  - **Catálogo** (visible **solo para admins**): las 4 categorías con sus opciones (activa/inactiva,
    origen `c3`/`manual`), un input para agregar y el botón **"Importar desde C3"**, que muestra
    cuántas opciones se agregaron.
- Diálogo de alta/edición (`components/manual-incident-form-dialog.tsx`):
  - Fecha (hoy por defecto) y hora (ahora por defecto).
  - Cliente, teléfono y agente.
  - Origen, tipo, ámbito y resultado con **combobox con búsqueda**: componente shadcn `combobox`
    sobre Base UI, que ya trae `Combobox` instalado en `node_modules/@base-ui/react`. Se agrega con
    `bunx shadcn@latest add combobox -y -o`.
  - Descripción (textarea).
- Catálogo vacío (primer deploy): aviso "Un admin debe importar el catálogo desde C3". Los admins
  ven el botón de importar ahí mismo.

### 7. `/usuarios` (frontend)

- El diálogo "Nuevo usuario" reemplaza el switch "Es administrador" por un select **Rol**:
  Administrador / Usuario / Solo incidencias.
- En la tabla, la columna Rol pasa a ser un select editable para admins. Llama al `PATCH` y
  deshabilita el select de la propia fila. Los errores `400`/`409` se muestran como toast.

### 8. Rama y documentación

- El trabajo va en una rama nueva **`incidencias-manuales` creada desde `main`**. La rama actual
  (`benchmarks-puntos-por-tiempo`) es de otra feature.
- Se actualizan `backend/CLAUDE.md` (roles, caché de roles, gap de tokens actualizado, dominio
  `incidents/`) y `frontend/CLAUDE.md` (`lib/access.ts`, providers condicionados al rol, la ruta
  nueva).

## Supuestos a confirmar

- **El rol `user` (acceso completo) también ve la sección nueva**, además de todo lo existente. Los
  admins ven todo, incluido el catálogo.
- **Campos de la incidencia** según la sección 4: fecha, hora, cliente, teléfono, agente, origen,
  tipo, ámbito, resultado y descripción. No hay campo "canal" (WhatsApp / llamada / correo /
  presencial); si lo quieren, puede ser una 5.ª categoría del catálogo, sin valores de C3.
- **Exportar** (PDF/JSON como en `/atenciones`) queda fuera de esta primera versión.

## Riesgos

- **Migración sobre el `users` en vivo**: es aditiva (una columna + backfill). El código viejo
  ignora `role` y sigue leyendo `is_admin`, que se mantiene sincronizado. Sin riesgo de pérdida de
  datos. Ojo con el reset recurrente e inexplicado de esa tabla en el Turso de dev: no tiene
  relación con esto, pero si ocurre durante las pruebas parecerá culpa de la migración.
- **Latencia**: la caché de roles agrega un viaje a Turso (~0,4 s) por usuario por minuto en
  cualquier endpoint. Es aceptable, pero se va a notar en el primer request de cada minuto.
- **Proceso único**: la caché de roles y su invalidación viven en memoria, igual que el lock de
  extracción y el rate limit. Ya está documentado que este servicio no escala horizontalmente; con
  varias réplicas, la invalidación no se propagaría (cada réplica tardaría ≤60 s).
- **Server functions accesibles por RPC**: un usuario restringido puede invocar
  `getAttentionsAnalytics` a mano, pero el backend responde `403`. Por eso el enforcement tiene que
  estar en el backend y testeado ahí.
- **PII**: las incidencias manuales guardan nombres y teléfonos de clientes; reciben el mismo
  tratamiento que los datos de C3. Las pruebas usan datos inventados.
- **Catálogo vacío** en el primer deploy: el formulario no sirve hasta que un admin importe.
  Mitigado con el aviso y el botón en la misma página.

## Archivos a tocar

Backend:

- `backend/app/auth/store.py`: columna `role`, migración, `create_user(role)`, `get_user_by_id`,
  `update_user_role`, `count_admins`.
- `backend/app/auth/security.py`: claim `role` (y derivación para tokens viejos).
- `backend/app/auth/dependencies.py`: caché de roles, `require_full_access`,
  `require_incidents_access`.
- `backend/app/routers/auth.py`: `role` en request/response, `PATCH /auth/users/{id}`.
- `backend/app/routers/runs.py`, `data.py`, `benchmarks.py`: dependencia del router →
  `require_full_access`.
- `backend/app/incidents/__init__.py`, `backend/app/incidents/store.py` (nuevos).
- `backend/app/extraction/store.py`: `distinct_incident_values`.
- `backend/app/routers/incidents.py` (nuevo) + `include_router` y tag en `backend/app/main.py`.
- Tests: `tests/auth/test_auth_store.py`, `tests/auth/test_security.py`, `tests/routers/test_auth.py`,
  `tests/incidents/test_incidents_store.py` (nuevo), `tests/routers/test_incidents.py` (nuevo), y
  gating por rol en `tests/routers/test_data.py`, `test_runs.py` y `test_benchmarks.py`.
- `backend/CLAUDE.md`.

Frontend:

- `frontend/src/server/schemas.ts`: `ROLES`, `UserRole`, `CurrentUser.role`, tipos y schemas de
  incidencia manual y catálogo, `manualIncidentsSearchSchema`.
- `frontend/src/server/backend.server.ts`: caché de sesión, fetchers de incidencias, catálogo y
  `PATCH` de rol.
- `frontend/src/server/auth.functions.ts`: `requireSession` devuelve el usuario, `updateUserRole`.
- `frontend/src/server/incidents.functions.ts` (nuevo).
- `frontend/src/lib/access.ts` (nuevo).
- `frontend/src/routes/__root.tsx`: contexto con `sessionUser`, redirect por rol, providers con
  `enabled`.
- `frontend/src/components/auto-refresh-provider.tsx`, `benchmark-schedule-provider.tsx`: prop
  `enabled`.
- `frontend/src/components/app-sidebar.tsx`: filtro por rol + ítem nuevo.
- `frontend/src/routes/incidencias-manuales.tsx` (nuevo).
- `frontend/src/components/manual-incident-form-dialog.tsx` (nuevo),
  `frontend/src/components/incident-catalog-card.tsx` (nuevo).
- `frontend/src/components/ui/combobox.tsx` (generado por shadcn), y `textarea` si hace falta.
- `frontend/src/routes/usuarios.tsx`: select de rol en el alta y en la tabla.
- `frontend/CLAUDE.md`.

## Verificación

Backend (`uv run pytest`, sin red, sqlite en memoria):

- Migración: una tabla `users` vieja sin `role` queda con `role` backfilleado desde `is_admin`;
  correrla dos veces no cambia nada.
- JWT: el token nuevo lleva `role`; un token viejo sin `role` se decodifica con el rol derivado.
- Gating: con rol `incidencias`, `/data/*`, `/extraction/*` y `/benchmarks/*` responden `403` y
  `/incidents/*` responde `200`. `user` y `admin` acceden a todo. Los endpoints del catálogo de
  admin responden `403` a `user` e `incidencias`.
- Caché de roles: el `PATCH` de rol aplica en el request siguiente; una cuenta borrada da `401`.
- `PATCH /auth/users/{id}`: `400` al cambiar el rol propio, `409` si deja cero admins.
- Incidencias: crear, editar y borrar (lógico); filtro por rango; las borradas no aparecen; se
  rechazan valores fuera del catálogo o inactivos; al editar se acepta el valor inactivo que la
  incidencia ya tenía.
- Importar desde C3: excluye `NULL`, `''`, `'-'` y `'N.A'`; es idempotente; no reactiva opciones
  desactivadas.

Frontend:

- `bun run typecheck` y `bun run check`.
- En el navegador, **contra un backend falso en Bun** (`C3_API_URL`), nunca contra el backend real:
  su arranque escribe en el Turso compartido y los timers del frontend pegan a C3 y al LLM.
  - Como `incidencias`: el sidebar muestra solo "Incidencias manuales"; ir a `/atenciones`, `/` o
    `/status` redirige a la sección; el log del backend falso **no** registra
    `POST /extraction/refresh` ni corridas de benchmarks; alta, edición y borrado funcionan; la
    pestaña Catálogo no aparece.
  - Como `admin`: ve todas las secciones y la pestaña Catálogo (agregar, desactivar, importar);
    cambia el rol de un usuario desde `/usuarios`.
  - El filtro de fechas arranca en hoy y no ofrece "todas".
