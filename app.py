from ldap3 import Server, Connection, ALL, SUBTREE

AD_SERVER = "192.168.92.131"
AD_USER = "Administrator@local.empresa"
AD_PASSWORD = "LabAD@Server2026!"
BASE_DN = "DC=local,DC=empresa"

server = Server(AD_SERVER, get_info=ALL)

conn = Connection(
    server,
    user=AD_USER,
    password=AD_PASSWORD,
    auto_referrals=False,
    auto_bind=True
)

print("Conectado ao Active Directory!")

consultas = [
    (
        "USUÁRIOS",
        "(&(objectCategory=person)(objectClass=user))",
        ["cn", "sAMAccountName", "mail"],
    ),
    (
        "OUS",
        "(objectClass=organizationalUnit)",
        ["ou", "description"],
    ),
    (
        "GRUPOS",
        "(objectClass=group)",
        ["cn", "sAMAccountName", "description"],
    ),
]

for titulo, filtro, atributos in consultas:
    conn.search(
        search_base=BASE_DN,
        search_filter=filtro,
        search_scope=SUBTREE,
        attributes=atributos,
    )

    print(f"\n=== {titulo} ({len(conn.entries)}) ===")
    for entry in conn.entries:
        print(entry)

conn.unbind()
