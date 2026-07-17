"""
End-to-end auth flow tests through the real HTTP stack (SQLite-backed).

These exercise endpoint -> service -> repository -> DB, verifying the
SECURITY BEHAVIORS, not just happy paths: rotation, reuse detection,
anti-enumeration, session revocation on password reset, RBAC boundaries.
"""

SIGNUP = {
    "email": "ankur@acme.com",
    "password": "Str0ng-pass!",
    "full_name": "Ankur Sharma",
    "organization_name": "Acme Corp",
}


def do_signup(client, **overrides):
    return client.post("/api/v1/auth/signup", json={**SIGNUP, **overrides})


def do_login(client, email=SIGNUP["email"], password=SIGNUP["password"]):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


class TestSignup:
    def test_signup_creates_admin_of_new_org(self, auth_client):
        resp = do_signup(auth_client)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["email"] == "ankur@acme.com"
        assert data["role"] == "admin"          # first user owns the workspace
        assert "password" not in resp.text      # no hash leakage, ever

    def test_duplicate_email_conflict(self, auth_client):
        do_signup(auth_client)
        resp = do_signup(auth_client, organization_name="Other Org")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    def test_weak_password_rejected_by_validation(self, auth_client):
        resp = do_signup(auth_client, password="short")
        assert resp.status_code == 422

    def test_invalid_email_rejected(self, auth_client):
        resp = do_signup(auth_client, email="not-an-email")
        assert resp.status_code == 422


class TestLogin:
    def test_login_returns_token_pair(self, auth_client):
        do_signup(auth_client)
        resp = do_login(auth_client)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 30 * 60
        assert data["access_token"] != data["refresh_token"]

    def test_wrong_password_and_unknown_email_same_error(self, auth_client):
        """Anti-enumeration: both failures look identical to the caller."""
        do_signup(auth_client)
        wrong_pw = do_login(auth_client, password="Wrong-pass-1!")
        no_user = do_login(auth_client, email="ghost@acme.com")
        assert wrong_pw.status_code == no_user.status_code == 401
        assert wrong_pw.json()["error"] == no_user.json()["error"]

    def test_login_email_is_case_insensitive(self, auth_client):
        do_signup(auth_client)
        assert do_login(auth_client, email="ANKUR@ACME.COM").status_code == 200


class TestProtectedRoutes:
    def test_me_requires_token(self, auth_client):
        assert auth_client.get("/api/v1/auth/me").status_code == 401

    def test_me_with_valid_token(self, auth_client):
        do_signup(auth_client)
        token = do_login(auth_client).json()["data"]["access_token"]
        resp = auth_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "ankur@acme.com"

    def test_garbage_token_rejected(self, auth_client):
        resp = auth_client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"}
        )
        assert resp.status_code == 401


class TestRefreshRotation:
    def test_refresh_issues_new_pair(self, auth_client):
        do_signup(auth_client)
        old = do_login(auth_client).json()["data"]
        resp = auth_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["refresh_token"] != old["refresh_token"]

    def test_used_refresh_token_cannot_be_replayed(self, auth_client):
        """Rotation: each refresh token works exactly once."""
        do_signup(auth_client)
        first = do_login(auth_client).json()["data"]["refresh_token"]
        auth_client.post("/api/v1/auth/refresh", json={"refresh_token": first})
        replay = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": first})
        assert replay.status_code == 401

    def test_reuse_detection_kills_all_sessions(self, auth_client):
        """Replaying a burned token must revoke the WHOLE family."""
        do_signup(auth_client)
        stolen = do_login(auth_client).json()["data"]["refresh_token"]
        # Legitimate rotation gives the user a fresh token...
        fresh = (
            auth_client.post("/api/v1/auth/refresh", json={"refresh_token": stolen})
            .json()["data"]["refresh_token"]
        )
        # ...then the OLD (stolen) one gets replayed by an attacker:
        auth_client.post("/api/v1/auth/refresh", json={"refresh_token": stolen})
        # The fresh token must now ALSO be dead (all sessions revoked).
        resp = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": fresh})
        assert resp.status_code == 401


class TestLogout:
    def test_logout_revokes_refresh_token(self, auth_client):
        do_signup(auth_client)
        rt = do_login(auth_client).json()["data"]["refresh_token"]
        assert (
            auth_client.post("/api/v1/auth/logout", json={"refresh_token": rt}).status_code
            == 200
        )
        resp = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        assert resp.status_code == 401

    def test_logout_is_idempotent(self, auth_client):
        resp = auth_client.post(
            "/api/v1/auth/logout", json={"refresh_token": "x" * 40}
        )
        assert resp.status_code == 200  # unknown token -> still "logged out"


class TestPasswordReset:
    def _request_reset_and_grab_token(self, auth_client, db_session_factory) -> str:
        """The reset token normally travels by email; tests read its HASH
        from the DB and cannot reverse it — so we capture the raw token by
        patching is impossible here. Instead we exercise the REAL flow:
        ask the service directly (same code path the endpoint calls)."""
        from app.services.auth_service import AuthService

        captured: dict = {}

        class CapturingSender:
            def send_password_reset(self, *, to_email: str, reset_link: str) -> None:
                captured["link"] = reset_link

        with db_session_factory() as db:
            AuthService(db, CapturingSender()).forgot_password(email=SIGNUP["email"])
        return captured["link"].split("token=")[1]

    def test_forgot_password_never_reveals_existence(self, auth_client):
        resp = auth_client.post(
            "/api/v1/auth/forgot-password", json={"email": "ghost@nowhere.com"}
        )
        assert resp.status_code == 200  # same success shape as a real account

    def test_full_reset_flow(self, auth_client, db_session_factory):
        do_signup(auth_client)
        old_refresh = do_login(auth_client).json()["data"]["refresh_token"]
        raw_token = self._request_reset_and_grab_token(auth_client, db_session_factory)

        resp = auth_client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "new_password": "N3w-Str0ng-pass!"},
        )
        assert resp.status_code == 200

        # Old password dead, new password works.
        assert do_login(auth_client).status_code == 401
        assert do_login(auth_client, password="N3w-Str0ng-pass!").status_code == 200
        # Every pre-reset session was revoked.
        resp = auth_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        assert resp.status_code == 401

    def test_reset_token_single_use(self, auth_client, db_session_factory):
        do_signup(auth_client)
        raw_token = self._request_reset_and_grab_token(auth_client, db_session_factory)
        auth_client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "new_password": "N3w-Str0ng-pass!"},
        )
        replay = auth_client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "new_password": "An0ther-pass!"},
        )
        assert replay.status_code == 401

    def test_bogus_reset_token_rejected(self, auth_client):
        resp = auth_client.post(
            "/api/v1/auth/reset-password",
            json={"token": "b" * 40, "new_password": "N3w-Str0ng-pass!"},
        )
        assert resp.status_code == 401


class TestRBAC:
    def test_require_roles_blocks_lower_role(self, auth_app, db_session_factory):
        """Wire a throwaway admin-only route and hit it as an employee."""
        from fastapi.testclient import TestClient

        from app.core.dependencies import AdminUser
        from app.models import User
        from app.models.enums import UserRole

        @auth_app.get("/_test/admin-only")
        def admin_only(user: AdminUser):
            return {"ok": True}

        client = TestClient(auth_app, raise_server_exceptions=False)
        do_signup(client)  # admin (workspace owner)

        # Demote the user directly in the DB to simulate an employee.
        with db_session_factory() as db:
            user = db.query(User).one()
            user.role = UserRole.EMPLOYEE
            db.commit()

        token = do_login(client).json()["data"]["access_token"]
        resp = client.get(
            "/_test/admin-only", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403
        assert "admin" in resp.json()["error"]["message"]

    def test_deactivated_user_blocked_even_with_valid_token(
        self, auth_app, db_session_factory
    ):
        """Fresh DB check beats the 30-min JWT window."""
        from fastapi.testclient import TestClient

        from app.models import User

        client = TestClient(auth_app, raise_server_exceptions=False)
        do_signup(client)
        token = do_login(client).json()["data"]["access_token"]

        with db_session_factory() as db:
            db.query(User).one().is_active = False
            db.commit()

        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403  # token still cryptographically valid!
