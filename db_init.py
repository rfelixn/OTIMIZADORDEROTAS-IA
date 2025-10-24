from models import get_engine_and_session, User, Delivery
from werkzeug.security import generate_password_hash

engine, Session = get_engine_and_session()
session = Session()

if not session.query(User).filter_by(username='admin').first():
    u = User(username='admin', password=generate_password_hash('admin123'), is_admin=True)
    session.add(u)
    session.commit()
    print('Admin criado: admin / admin123')

if session.query(Delivery).count() == 0:
    samples = [
        ('Praça do Comércio, Lisboa', 'Lisboa', 'Entregar na recepção'),
        ('Av. da Liberdade 200, Lisboa', 'Lisboa', 'Portaria 24h'),
        ('Rua Augusta 50, Lisboa', 'Lisboa', 'Loja 2'),
        ('Avenida dos Aliados, Porto', 'Porto', 'Praça central')
    ]
    for addr, city, notes in samples:
        d = Delivery(address=addr, city=city, notes=notes)
        session.add(d)
    session.commit()
    print('Entregas de exemplo criadas')

session.close()
