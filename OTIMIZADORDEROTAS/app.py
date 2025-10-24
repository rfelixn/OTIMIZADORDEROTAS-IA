from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import requests
import itertools
import io
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sua_chave_secreta_aqui'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ---------------------- MODELS ----------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))

class Delivery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    notes = db.Column(db.String(300))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)

# ---------------------- LOGIN ----------------------
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))  # ✅ SQLAlchemy 2.0

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        user = db.session.query(User).filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for('dashboard'))
        return render_template("login.html", error="Usuário ou senha incorretos")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ---------------------- DASHBOARD ----------------------
@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    deliveries = db.session.query(Delivery).all()
    # ⚡ Transformar para JSON simples
    deliveries_json = [
        {"id": d.id, "address": d.address, "city": d.city, "notes": d.notes, "lat": d.lat, "lon": d.lon}
        for d in deliveries
    ]
    return render_template("dashboard.html", deliveries=deliveries, deliveries_json=deliveries_json)

@app.route("/nova_entrega", methods=["POST"])
@login_required
def nova_entrega():
    address = request.form['address']
    city = request.form.get('city', '')
    notes = request.form.get('notes', '')
    d = Delivery(address=address, city=city, notes=notes)
    db.session.add(d)
    db.session.commit()
    return redirect(url_for('dashboard'))

# ---------------------- GEOCODING ----------------------
@app.route("/geocode/<int:id>", methods=["POST"])
@login_required
def geocode(id):
    d = db.session.get(Delivery, id)  # ✅ SQLAlchemy 2.0
    if not d:
        return jsonify({"ok": False})
    try:
        query = f"{d.address} {d.city}".strip()
        url = "https://nominatim.openstreetmap.org/search"
        res = requests.get(url, params={"q": query, "format": "json"}).json()
        if res:
            d.lat = float(res[0]["lat"])
            d.lon = float(res[0]["lon"])
            db.session.commit()
            return jsonify({"ok": True})
    except Exception as e:
        print("Erro no geocode:", e)
    return jsonify({"ok": False})

# ---------------------- ABRIR MAPS/WAZE ----------------------
@app.route("/open_waze/<int:id>")
@login_required
def open_waze(id):
    d = db.session.get(Delivery, id)
    if d and d.lat and d.lon:
        return redirect(f"https://waze.com/ul?ll={d.lat}%2C{d.lon}&navigate=yes")
    return redirect(url_for('dashboard'))

@app.route("/open_maps/<int:id>")
@login_required
def open_maps(id):
    d = db.session.get(Delivery, id)
    if d and d.lat and d.lon:
        return redirect(f"https://www.google.com/maps/search/?api=1&query={d.lat},{d.lon}")
    return redirect(url_for('dashboard'))

# ---------------------- OTIMIZAÇÃO DE ROTAS ----------------------
@app.route("/api/optimize", methods=["POST"])
@login_required
def optimize():
    data = request.get_json()
    start = data.get("start")
    ids = data.get("ids", [])
    if not start or not ids:
        return jsonify({"error": "Parâmetros inválidos"})

    deliveries = [db.session.get(Delivery, i) for i in ids]
    deliveries = [d for d in deliveries if d and d.lat and d.lon]

    if not deliveries:
        return jsonify({"error": "Nenhuma entrega válida"})

    best_order = None
    min_dist = float('inf')
    for perm in itertools.permutations(deliveries):
        dist = 0
        prev = start
        for d in perm:
            dist += ((prev["lat"]-d.lat)**2 + (prev["lon"]-d.lon)**2)**0.5
            prev = {"lat": d.lat, "lon": d.lon}
        if dist < min_dist:
            min_dist = dist
            best_order = [d.id for d in perm]

    return jsonify({"order": best_order})

# ---------------------- EXPORTAR PDF ----------------------
@app.route("/export_pdf")
@login_required
def export_pdf():
    deliveries = db.session.query(Delivery).all()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.setFont("Helvetica", 12)
    y = 800
    c.drawString(50, y, f"Relatório de entregas - Usuário: {current_user.username}")
    y -= 30
    for d in deliveries:
        line = f"#{d.id} - {d.address}, {d.city or ''} - {d.notes or ''} - ({d.lat},{d.lon})"
        c.drawString(50, y, line)
        y -= 20
        if y < 50:
            c.showPage()
            y = 800
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="entregas.pdf", mimetype='application/pdf')

# ---------------------- INICIALIZAÇÃO ----------------------
if __name__ == "__main__":
    # Cria o banco se não existir
    with app.app_context():
        db.create_all()
    app.run(debug=True)
