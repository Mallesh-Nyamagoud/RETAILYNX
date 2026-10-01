import sys
from app.services.auth import get_user_by_email, add_user, get_db

email = 'mis@adonisgroup.in'
user = get_user_by_email(email)

if user:
    with get_db() as conn:
        conn.execute("UPDATE users SET role = 'ADMIN' WHERE email = ?", (email,))
        conn.commit()
    print(f'Updated {email} to ADMIN')
else:
    add_user(email, 'ADMIN')
    print(f'Created {email} as ADMIN')
