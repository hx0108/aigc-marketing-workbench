import argparse,getpass,uuid
from .db import initialize, Session
from .auth import Account,password_hash,LoginSession
from . import execution
from sqlalchemy import delete
p=argparse.ArgumentParser();p.add_argument('username');args=p.parse_args()
from .db import engine
if engine.dialect.name=='postgresql':
    from .migrate import migrate
    migrate()
else:initialize()
with Session() as s:
    row=s.get(Account,args.username)
    if row:
        row.password_hash=password_hash(getpass.getpass('New password: '));s.execute(delete(LoginSession).where(LoginSession.workspace==row.workspace))
    else:s.add(Account(username=args.username,workspace=str(uuid.uuid4()),password_hash=password_hash(getpass.getpass('Password: '))))
    s.commit()

