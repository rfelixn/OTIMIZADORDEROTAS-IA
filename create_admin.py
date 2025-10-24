from models import get_engine_and_session, User
from werkzeug.security import generate_password_hash
import sys

if len(sys.argv) < 3:
    print('Uso: python create_admin.py USER PASSWORD')
    sys.exit(1)
username = sys.argv[1]
password = sys.argv[2]
engine, Session = get_engine_and_session()
session = Session()
if session.query(User).filter_by(username=username).first():
    print('Usuário já existe')
else:
    u = User(username=username, password=generate_password_hash(password), is_admin=True)
    session.add(u)
    session.commit()
    print('Usuário criado:', username)
session.close()
