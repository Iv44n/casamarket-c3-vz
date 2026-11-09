import pytest

from app.auth import dependencies

# Un endpoint representativo por router "de acceso completo" -- todos tienen el gating a nivel
# de APIRouter(dependencies=[...]), asi que basta uno por router.
FULL_ACCESS_ENDPOINTS = [
    "/extraction/status",
    "/data/attention",
    "/benchmarks/run/status",
]


@pytest.mark.parametrize("path", FULL_ACCESS_ENDPOINTS)
def test_incidents_role_gets_403_on_every_existing_router(api, path: str):
    headers = api.user_headers("rosa", "incidencias")

    response = api.client.get(path, headers=headers)

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["admin", "user"])
def test_full_access_roles_can_use_the_existing_routers(api, role: str):
    headers = api.user_headers("ana", role)

    response = api.client.get("/extraction/status", headers=headers)

    assert response.status_code == 200


@pytest.mark.parametrize("role", ["admin", "user", "incidencias"])
def test_every_role_can_use_the_incidents_router(api, role: str):
    headers = api.user_headers("ana", role)

    response = api.client.get(
        "/incidents", params={"date_from": "2026-11-09", "date_to": "2026-11-09"}, headers=headers
    )

    assert response.status_code == 200


def test_a_forged_role_claim_does_not_grant_access(api):
    """El rol se re-lee de la DB: un token que dice "admin" para una cuenta "incidencias"
    (o un token viejo de antes de un cambio de rol) no alcanza."""
    rosa = api.create_user("rosa", "incidencias")

    response = api.client.get("/extraction/status", headers=api.headers_for(rosa, "admin"))

    assert response.status_code == 403


def test_a_role_change_applies_on_the_very_next_request(api):
    admin_headers = api.user_headers("boss", "admin")
    luis = api.create_user("luis", "user")
    luis_headers = api.headers_for(luis)
    assert api.client.get("/extraction/status", headers=luis_headers).status_code == 200

    patched = api.client.patch(
        f"/auth/users/{luis.id}", json={"role": "incidencias"}, headers=admin_headers
    )

    assert patched.status_code == 200
    # Mismo token viejo (sigue diciendo role=user): el PATCH invalido la cache de roles.
    assert api.client.get("/extraction/status", headers=luis_headers).status_code == 403


def test_a_token_for_a_deleted_account_gets_401(api):
    luis = api.create_user("luis", "user")
    headers = api.headers_for(luis)
    conn = dependencies.store.get_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (luis.id,))
    conn.commit()
    conn.close()

    response = api.client.get("/extraction/status", headers=headers)

    assert response.status_code == 401


def test_a_token_whose_user_id_now_belongs_to_someone_else_gets_401(api):
    """Si la tabla users se recrea (AUTOINCREMENT vuelve a 1), un token viejo no debe heredar
    los permisos de quien sea el nuevo dueño de ese id."""
    boss = api.create_user("boss", "admin")
    stale_headers = api.headers_for(boss)
    conn = dependencies.store.get_connection()
    conn.execute("UPDATE users SET username = 'otra' WHERE id = ?", (boss.id,))
    conn.commit()
    conn.close()

    response = api.client.get("/extraction/status", headers=stale_headers)

    assert response.status_code == 401


def test_the_role_cache_expires_after_its_ttl(api, monkeypatch: pytest.MonkeyPatch):
    """Un cambio de rol hecho por fuera de PATCH (p.ej. a mano en Turso) aplica a lo sumo un
    TTL despues."""
    clock = [1000.0]
    monkeypatch.setattr(dependencies.time, "monotonic", lambda: clock[0])
    luis = api.create_user("luis", "user")
    headers = api.headers_for(luis)
    assert api.client.get("/extraction/status", headers=headers).status_code == 200
    conn = dependencies.store.get_connection()
    conn.execute("UPDATE users SET role = 'incidencias' WHERE id = ?", (luis.id,))
    conn.commit()
    conn.close()

    assert api.client.get("/extraction/status", headers=headers).status_code == 200  # cacheado

    clock[0] += dependencies._ROLE_CACHE_TTL_SECONDS + 1

    assert api.client.get("/extraction/status", headers=headers).status_code == 403


def test_patch_user_role_rejects_changing_your_own_role(api):
    boss = api.create_user("boss", "admin")

    response = api.client.patch(
        f"/auth/users/{boss.id}", json={"role": "user"}, headers=api.headers_for(boss)
    )

    assert response.status_code == 400


def test_patch_user_role_returns_404_for_an_unknown_user(api):
    response = api.client.patch(
        "/auth/users/999", json={"role": "user"}, headers=api.user_headers("boss", "admin")
    )

    assert response.status_code == 404


def test_patch_user_role_requires_admin(api):
    luis = api.create_user("luis", "user")

    response = api.client.patch(
        f"/auth/users/{luis.id}", json={"role": "admin"}, headers=api.headers_for(luis)
    )

    assert response.status_code == 403


def test_create_user_with_the_incidents_role_and_login_carries_it(api):
    admin_headers = api.user_headers("boss", "admin")

    created = api.client.post(
        "/auth/users",
        json={"username": "rosa", "password": "s3cret", "role": "incidencias"},
        headers=admin_headers,
    )
    login = api.client.post("/auth/login", json={"username": "rosa", "password": "s3cret"})
    me = api.client.get(
        "/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )

    assert created.status_code == 201
    assert created.json()["role"] == "incidencias"
    assert created.json()["is_admin"] is False
    assert me.json()["role"] == "incidencias"


def test_create_user_rejects_an_unknown_role(api):
    response = api.client.post(
        "/auth/users",
        json={"username": "rosa", "password": "s3cret", "role": "superuser"},
        headers=api.user_headers("boss", "admin"),
    )

    assert response.status_code == 422


def test_patch_user_can_rename_and_reset_password(api):
    admin_headers = api.user_headers("boss", "admin")
    luis = api.create_user("luis", "user")
    old_headers = api.headers_for(luis)

    response = api.client.patch(
        f"/auth/users/{luis.id}",
        json={"username": "Luis.Gomez", "password": "nueva-clave"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["username"] == "luis.gomez"
    login = api.client.post(
        "/auth/login", json={"username": "luis.gomez", "password": "nueva-clave"}
    )
    assert login.status_code == 200
    # El token emitido con el username viejo deja de servir: tiene que volver a entrar.
    assert api.client.get("/extraction/status", headers=old_headers).status_code == 401


def test_patch_user_rename_to_an_existing_username_returns_409(api):
    admin_headers = api.user_headers("boss", "admin")
    api.create_user("luis", "user")
    ana = api.create_user("ana", "user")

    response = api.client.patch(
        f"/auth/users/{ana.id}", json={"username": "luis"}, headers=admin_headers
    )

    assert response.status_code == 409


def test_patch_user_with_no_changes_returns_400(api):
    admin_headers = api.user_headers("boss", "admin")
    ana = api.create_user("ana", "user")

    response = api.client.patch(f"/auth/users/{ana.id}", json={}, headers=admin_headers)

    assert response.status_code == 400


def test_admin_can_change_only_the_password_of_their_own_account(api):
    boss = api.create_user("boss", "admin")
    headers = api.headers_for(boss)

    renamed = api.client.patch(
        f"/auth/users/{boss.id}", json={"username": "otro"}, headers=headers
    )
    password = api.client.patch(
        f"/auth/users/{boss.id}", json={"password": "nueva", "username": "BOSS"}, headers=headers
    )

    assert renamed.status_code == 400
    assert password.status_code == 200
    assert (
        api.client.post("/auth/login", json={"username": "boss", "password": "nueva"}).status_code
        == 200
    )


def test_delete_user_revokes_access_on_the_next_request(api):
    admin_headers = api.user_headers("boss", "admin")
    luis = api.create_user("luis", "user")
    luis_headers = api.headers_for(luis)
    assert api.client.get("/extraction/status", headers=luis_headers).status_code == 200

    response = api.client.delete(f"/auth/users/{luis.id}", headers=admin_headers)

    assert response.status_code == 204
    assert api.client.get("/extraction/status", headers=luis_headers).status_code == 401
    assert [u["username"] for u in api.client.get("/auth/users", headers=admin_headers).json()] == [
        "boss"
    ]


def test_delete_user_rejects_your_own_account(api):
    boss = api.create_user("boss", "admin")

    response = api.client.delete(f"/auth/users/{boss.id}", headers=api.headers_for(boss))

    assert response.status_code == 400


def test_delete_user_returns_404_for_an_unknown_user(api):
    response = api.client.delete("/auth/users/999", headers=api.user_headers("boss", "admin"))

    assert response.status_code == 404


@pytest.mark.parametrize("role", ["user", "incidencias"])
def test_delete_user_requires_admin(api, role: str):
    target = api.create_user("luis", "user")

    response = api.client.delete(
        f"/auth/users/{target.id}", headers=api.user_headers("ana", role)
    )

    assert response.status_code == 403
