import os
from contextlib import contextmanager
from datetime import date, datetime, time, timezone

from ldap3 import ALL, MODIFY_ADD, MODIFY_DELETE, MODIFY_REPLACE, SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPBindError, LDAPSocketOpenError
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import escape_rdn
from dotenv import load_dotenv


load_dotenv()


class ADOperationError(RuntimeError):
    pass


class ActiveDirectoryService:
    """Active Directory operations using connection settings from the environment."""

    def __init__(self):
        settings = {
            "AD_SERVER": os.getenv("AD_SERVER"),
            "AD_PORT": os.getenv("AD_PORT", "389"),
            "AD_USE_SSL": os.getenv("AD_USE_SSL", "false"),
            "AD_USER": os.getenv("AD_USER"),
            "AD_PASSWORD": os.getenv("AD_PASSWORD"),
            "AD_BASE_DN": os.getenv("AD_BASE_DN"),
        }
        missing = [name for name, value in settings.items() if not value]
        if missing:
            raise RuntimeError(f"Missing required environment setting(s): {', '.join(missing)}")

        self.server_address = settings["AD_SERVER"]
        try:
            self.server_port = int(settings["AD_PORT"])
        except ValueError as exc:
            raise RuntimeError("AD_PORT must be a valid integer") from exc
        self.use_ssl = settings["AD_USE_SSL"].strip().lower() in {"1", "true", "yes", "on"}
        self.bind_user = settings["AD_USER"]
        self.bind_password = settings["AD_PASSWORD"]
        self.base_dn = settings["AD_BASE_DN"]

    @contextmanager
    def connection(self):
        conn = None
        try:
            server = Server(
                self.server_address,
                port=self.server_port,
                use_ssl=self.use_ssl,
                get_info=ALL,
                connect_timeout=5,
            )
            conn = Connection(
                server,
                user=self.bind_user,
                password=self.bind_password,
                auto_referrals=False,
                auto_bind=True,
            )
            yield conn
        except LDAPSocketOpenError as exc:
            technical_detail = str(exc)
            if self.use_ssl and ("ssl wrapping error" in technical_detail.lower() or "10054" in technical_detail):
                raise ADOperationError(
                    f"A porta LDAPS {self.server_address}:{self.server_port} está acessível, "
                    f"mas o Windows Server encerrou o handshake TLS. Verifique se o controlador "
                    f"de domínio possui um certificado LDAPS válido, com chave privada e uso "
                    f"Server Authentication. Valide a conexão pelo ldp.exe usando SSL. "
                    f"Detalhe técnico: {technical_detail}"
                ) from exc
            raise ADOperationError(
                f"Não foi possível acessar o servidor LDAP em "
                f"{self.server_address}:{self.server_port}. O servidor pode estar ligado, mas a porta LDAP "
                f"não está acessível a partir desta máquina. Verifique o firewall do "
                f"Windows Server e teste: Test-NetConnection {self.server_address} -Port {self.server_port}. "
                f"Detalhe técnico: {technical_detail}"
            ) from exc
        except LDAPBindError as exc:
            raise ADOperationError(
                f"O servidor LDAP {self.server_address}:{self.server_port} foi alcançado, mas recusou a "
                f"autenticação. Verifique AD_USER e AD_PASSWORD. Detalhe técnico: {exc}"
            ) from exc
        except ADOperationError:
            raise
        except Exception as exc:
            raise ADOperationError(
                f"Falha inesperada ao conectar ao Active Directory em "
                f"{self.server_address}:{self.server_port}: {exc}"
            ) from exc
        finally:
            if conn and conn.bound:
                conn.unbind()

    @staticmethod
    def _values(entry, attribute):
        if attribute not in entry.entry_attributes:
            return []
        value = entry[attribute].value
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    @classmethod
    def _value(cls, entry, attribute, default=""):
        values = cls._values(entry, attribute)
        return values[0] if values else default

    @staticmethod
    def _parent_dn(dn):
        return dn.split(",", 1)[1] if "," in dn else ""

    def _search(self, search_filter, attributes, search_base=None):
        with self.connection() as conn:
            ok = conn.search(
                search_base=search_base or self.base_dn,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=attributes,
            )
            if not ok and conn.result.get("result") != 0:
                self._raise_result(conn, "Search failed")
            return list(conn.entries)

    @staticmethod
    def _raise_result(conn, message):
        detail = conn.result.get("message") or conn.result.get("description") or "Unknown LDAP error"
        raise ADOperationError(f"{message}: {detail}")

    @staticmethod
    def _require(data, *fields):
        missing = [field for field in fields if not str(data.get(field, "")).strip()]
        if missing:
            raise ValueError(f"Required field(s): {', '.join(missing)}")

    def list_users(self):
        entries = self._search(
            "(&(objectCategory=person)(objectClass=user))",
            ["cn", "displayName", "givenName", "sn", "sAMAccountName", "userPrincipalName", "distinguishedName", "userAccountControl", "pwdLastSet", "lockoutTime", "accountExpires", "memberOf", "mail", "description"],
        )
        return [self._user(entry) for entry in entries]

    def get_user(self, identifier):
        entry = self._find_one(identifier, "user", ["cn", "displayName", "givenName", "sn", "sAMAccountName", "userPrincipalName", "distinguishedName", "userAccountControl", "pwdLastSet", "lockoutTime", "accountExpires", "memberOf", "mail", "description"])
        return self._user(entry)

    def _user(self, entry):
        dn = entry.entry_dn
        control = int(self._value(entry, "userAccountControl", 0))
        return {
            "id": dn,
            "name": self._value(entry, "displayName") or self._value(entry, "cn"),
            "firstName": self._value(entry, "givenName"),
            "lastName": self._value(entry, "sn"),
            "username": self._value(entry, "sAMAccountName"),
            "upn": self._value(entry, "userPrincipalName"),
            "dn": dn,
            "ou": self._parent_dn(dn),
            "enabled": not bool(control & 2),
            "mustChangePassword": self._ad_integer(self._value(entry, "pwdLastSet", 0)) == 0,
            "passwordNeverExpires": bool(control & 0x10000),
            "reversiblePasswordEncryption": bool(control & 0x80),
            "locked": self._ad_integer(self._value(entry, "lockoutTime", 0)) > 0,
            "accountExpires": self._filetime_to_date(self._value(entry, "accountExpires", 0)),
            "groups": self._values(entry, "memberOf"),
            "email": self._value(entry, "mail"),
            "description": self._value(entry, "description"),
        }

    def create_user(self, data):
        self._require(data, "name", "username", "password", "ouDn")
        name = str(data["name"]).strip()
        username = str(data["username"]).strip()
        dn = f"CN={escape_rdn(name)},{data['ouDn']}"
        parts = name.split(None, 1)
        attributes = {
            "cn": name,
            "displayName": name,
            "givenName": data.get("firstName") or parts[0],
            "sn": data.get("lastName") or (parts[1] if len(parts) > 1 else parts[0]),
            "sAMAccountName": username,
            "userPrincipalName": data.get("upn") or f"{username}@{self._domain_name()}",
            "userAccountControl": 514,
        }
        for key, source in (("mail", "email"), ("description", "description")):
            if data.get(source):
                attributes[key] = data[source]
        with self.connection() as conn:
            if not conn.add(dn, ["top", "person", "organizationalPerson", "user"], attributes):
                self._raise_result(conn, "Could not create user")
            if not conn.extend.microsoft.modify_password(dn, data["password"]):
                password_result = dict(conn.result)
                rollback_ok = conn.delete(dn)
                detail = (
                    password_result.get("message")
                    or password_result.get("description")
                    or "Unknown LDAP error"
                )
                rollback_status = "rollback completed" if rollback_ok else "rollback also failed"
                raise ADOperationError(
                    f"Could not set initial password ({detail}); {rollback_status}"
                )
            if data.get("enabled", True) and not conn.modify(dn, {"userAccountControl": [(MODIFY_REPLACE, [512])]}):
                self._raise_result(conn, "User created, but could not be enabled")
        return self.get_user(dn)

    def update_user(self, identifier, data):
        dn = self._resolve_dn(identifier, "user")
        mapping = {"name": "displayName", "firstName": "givenName", "lastName": "sn", "username": "sAMAccountName", "upn": "userPrincipalName", "email": "mail", "description": "description"}
        changes = {ldap_name: [(MODIFY_REPLACE, [data[key]] if data.get(key) not in (None, "") else [])] for key, ldap_name in mapping.items() if key in data}
        if changes:
            with self.connection() as conn:
                if not conn.modify(dn, changes):
                    self._raise_result(conn, "Could not update user")
        account_changes = {}
        if "passwordNeverExpires" in data or "reversiblePasswordEncryption" in data:
            entry = self._find_one(dn, "user", ["userAccountControl"])
            control = int(self._value(entry, "userAccountControl", 512))
            for field, flag in (("passwordNeverExpires", 0x10000), ("reversiblePasswordEncryption", 0x80)):
                if field in data:
                    control = control | flag if bool(data[field]) else control & ~flag
            account_changes["userAccountControl"] = [(MODIFY_REPLACE, [control])]
        if "mustChangePassword" in data:
            current = self._find_one(dn, "user", ["pwdLastSet"])
            currently_required = self._ad_integer(self._value(current, "pwdLastSet", 0)) == 0
            if bool(data["mustChangePassword"]) != currently_required:
                account_changes["pwdLastSet"] = [(MODIFY_REPLACE, [0 if data["mustChangePassword"] else -1])]
        if data.get("unlockAccount"):
            account_changes["lockoutTime"] = [(MODIFY_REPLACE, [0])]
        if "accountExpires" in data:
            account_changes["accountExpires"] = [(MODIFY_REPLACE, [self._date_to_filetime(data["accountExpires"])])]
        if account_changes:
            with self.connection() as conn:
                if not conn.modify(dn, account_changes):
                    self._raise_result(conn, "Could not update account options")
        return self.get_user(dn)

    @staticmethod
    def _filetime_to_date(value):
        if isinstance(value, datetime):
            return value.date().isoformat()
        value = ActiveDirectoryService._ad_integer(value)
        if value in (0, 9223372036854775807):
            return ""
        seconds = value / 10_000_000 - 11_644_473_600
        return datetime.fromtimestamp(seconds, timezone.utc).date().isoformat()

    @staticmethod
    def _ad_integer(value):
        if not value:
            return 0
        if isinstance(value, datetime):
            value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return int((value.timestamp() + 11_644_473_600) * 10_000_000)
        return int(value)

    @staticmethod
    def _date_to_filetime(value):
        if not value:
            return 0
        try:
            expires = datetime.combine(date.fromisoformat(str(value)), time.min, timezone.utc)
        except ValueError as exc:
            raise ValueError("accountExpires must use YYYY-MM-DD format") from exc
        return int((expires.timestamp() + 11_644_473_600) * 10_000_000)

    def set_user_status(self, identifier, enabled):
        dn = self._resolve_dn(identifier, "user")
        entry = self._find_one(dn, "user", ["userAccountControl"])
        current = int(self._value(entry, "userAccountControl", 512))
        value = current & ~2 if enabled else current | 2
        with self.connection() as conn:
            if not conn.modify(dn, {"userAccountControl": [(MODIFY_REPLACE, [value])]}):
                self._raise_result(conn, "Could not change account status")
        return self.get_user(dn)

    def reset_password(self, identifier, password):
        if not password or len(password) < 8:
            raise ValueError("Password must contain at least 8 characters")
        dn = self._resolve_dn(identifier, "user")
        with self.connection() as conn:
            if not conn.extend.microsoft.modify_password(dn, password):
                self._raise_result(conn, "Could not reset password")

    def list_ous(self):
        return [self._ou(entry) for entry in self._search("(objectClass=organizationalUnit)", ["ou", "distinguishedName", "description"])]

    def get_ou(self, identifier):
        return self._ou(self._find_one(identifier, "organizationalUnit", ["ou", "distinguishedName", "description"]))

    def _ou(self, entry):
        dn = entry.entry_dn
        return {"id": dn, "name": self._value(entry, "ou"), "dn": dn, "parentOu": self._parent_dn(dn), "description": self._value(entry, "description")}

    def create_ou(self, data):
        self._require(data, "name")
        parent = data.get("parentDn") or self.base_dn
        dn = f"OU={escape_rdn(str(data['name']).strip())},{parent}"
        attributes = {"ou": data["name"]}
        if data.get("description"):
            attributes["description"] = data["description"]
        with self.connection() as conn:
            if not conn.add(dn, ["top", "organizationalUnit"], attributes):
                self._raise_result(conn, "Could not create OU")
        return self.get_ou(dn)

    def list_groups(self):
        return [self._group(entry) for entry in self._search("(objectClass=group)", ["cn", "sAMAccountName", "distinguishedName", "groupType", "member", "managedBy", "description"])]

    def get_group(self, identifier):
        return self._group(self._find_one(identifier, "group", ["cn", "sAMAccountName", "distinguishedName", "groupType", "member", "managedBy", "description"]))

    def _group(self, entry):
        group_type = int(self._value(entry, "groupType", 0))
        scope = "Universal" if group_type & 8 else "Domain Local" if group_type & 4 else "Global"
        category = "Security" if group_type & 0x80000000 else "Distribution"
        dn = entry.entry_dn
        return {"id": dn, "name": self._value(entry, "cn"), "username": self._value(entry, "sAMAccountName"), "dn": dn, "type": f"{scope} / {category}", "groupType": group_type, "members": self._values(entry, "member"), "managedBy": self._value(entry, "managedBy"), "description": self._value(entry, "description")}

    def create_group(self, data):
        self._require(data, "name", "ouDn")
        name = str(data["name"]).strip()
        dn = f"CN={escape_rdn(name)},{data['ouDn']}"
        attributes = {"cn": name, "sAMAccountName": data.get("username") or name, "groupType": int(data.get("groupType", -2147483646))}
        if data.get("description"):
            attributes["description"] = data["description"]
        with self.connection() as conn:
            if not conn.add(dn, ["top", "group"], attributes):
                self._raise_result(conn, "Could not create group")
        return self.get_group(dn)

    def update_group(self, identifier, data):
        dn = self._resolve_dn(identifier, "group")
        if data.get("name"):
            current_name = self.get_group(dn)["name"]
            if data["name"] != current_name:
                with self.connection() as conn:
                    if not conn.modify_dn(dn, f"CN={escape_rdn(str(data['name']).strip())}"):
                        self._raise_result(conn, "Could not rename group")
                dn = f"CN={escape_rdn(str(data['name']).strip())},{self._parent_dn(dn)}"
        mapping = {"username": "sAMAccountName", "description": "description", "groupType": "groupType"}
        changes = {ldap_name: [(MODIFY_REPLACE, [data[key]] if data.get(key) not in (None, "") else [])] for key, ldap_name in mapping.items() if key in data}
        if changes:
            with self.connection() as conn:
                if not conn.modify(dn, changes):
                    self._raise_result(conn, "Could not update group")
        return self.get_group(dn)

    def change_group_member(self, group_identifier, user_identifier, add=True):
        if not user_identifier:
            raise ValueError("userId is required")
        group_dn = self._resolve_dn(group_identifier, "group")
        user_dn = self._resolve_dn(user_identifier, "user")
        operation = MODIFY_ADD if add else MODIFY_DELETE
        with self.connection() as conn:
            if not conn.modify(group_dn, {"member": [(operation, [user_dn])]}):
                self._raise_result(conn, "Could not update group membership")
        return self.get_group(group_dn)

    def _find_one(self, identifier, object_class, attributes):
        safe = escape_filter_chars(identifier)
        if "=" in identifier and "," in identifier:
            search_filter = f"(&(objectClass={object_class})(distinguishedName={safe}))"
        else:
            search_filter = f"(&(objectClass={object_class})(|(sAMAccountName={safe})(cn={safe})(ou={safe})))"
        entries = self._search(search_filter, attributes)
        if not entries:
            raise LookupError(f"{object_class} not found")
        return entries[0]

    def _resolve_dn(self, identifier, object_class):
        return self._find_one(identifier, object_class, ["distinguishedName"]).entry_dn

    def _domain_name(self):
        return ".".join(part[3:] for part in self.base_dn.split(",") if part.upper().startswith("DC="))


ad_service = ActiveDirectoryService()
