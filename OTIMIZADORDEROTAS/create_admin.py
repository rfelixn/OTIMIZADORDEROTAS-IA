from app import app
from models import db, User

with app.app_context():
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='1234', name='Administrador')
        db.session.add(admin)
        db.session.commit()
    print("Admin criado com sucesso!")
