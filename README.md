# Active Directory Web Admin

A lightweight Flask application for viewing and managing Microsoft Active Directory through LDAP. The web interface provides dashboards and basic administration for users, organizational units, groups, account status, and passwords.

## Features

- List and manage AD users, groups, and organizational units
- Create and edit users
- Enable, disable, and unlock accounts
- Reset passwords and manage common account options
- Keep AD connection credentials on the server through environment variables

## Setup

Create a virtual environment, install the dependencies, and copy `.env.example` to `.env`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Configure the connection in `.env`:

```env
AD_SERVER=dc.example.local
AD_PORT=636
AD_USE_SSL=true
AD_USER=Administrator@example.local
AD_PASSWORD=replace-with-a-secure-password
AD_BASE_DN=DC=example,DC=local
PORT=5051
```

Run the application:

```powershell
python app.py
```

Then open `http://localhost:5051`.

## LDAPS requirement

Use LDAPS on port `636` for password creation and reset operations. The domain controller must have a valid certificate with a private key and the `Server Authentication` purpose. Regular LDAP on port `389` may allow searches and object creation, but Active Directory normally refuses password changes over an unencrypted connection.

You can check connectivity from the application machine with:

```powershell
Test-NetConnection dc.example.local -Port 636
```

Do not commit the `.env` file or expose the AD password in frontend code or API responses.

## Screenshot

<img width="1904" height="871" alt="Active Directory Web Admin interface" src="https://github.com/user-attachments/assets/e877431e-0be2-4732-8232-4d4deefefe7f" />
