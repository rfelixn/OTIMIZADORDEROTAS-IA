from app import app, db, User

with app.app_context():
    db.create_all()

    # Criar usuário demo se não existir
    if not User.query.filter_by(username="entregador").first():
        u = User(username="entregador", password="1234")
        db.session.add(u)
        db.session.commit()
        print("Banco inicializado e usuário demo criado.")
    else:
        print("Usuário demo já existe.")
