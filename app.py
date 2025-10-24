import os, math, io, requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import check_password_hash
from models import get_engine_and_session, User, Delivery
from urllib.parse import quote_plus
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from ortools.constraint_solver import routing_enums_pb2, pywrapcp

GMAPS_KEY = os.environ.get('GOOGLE_API_KEY')
try:
    if GMAPS_KEY:
        import googlemaps
        gmaps = googlemaps.Client(key=GMAPS_KEY)
    else:
        gmaps = None
except Exception:
    gmaps = None

app = Flask(__name__)
app.secret_key = os.environ.get('APP_SECRET', 'troque_por_uma_chave_secreta')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

engine, Session = get_engine_and_session()

class UserLogin(UserMixin):
    def __init__(self, user):
        self.id = str(user.id)
        self.username = user.username

@login_manager.user_loader
def load_user(user_id):
    session = Session()
    u = session.get(User, int(user_id))
    session.close()
    if not u:
        return None
    return UserLogin(u)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        session = Session()
        u = session.query(User).filter_by(username=username).first()
        session.close()
        if u and check_password_hash(u.password, password):
            login_user(UserLogin(u))
            return redirect(url_for('dashboard'))
        flash('Usuário ou senha inválidos', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
def home():
    return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    session = Session()
    deliveries = session.query(Delivery).order_by(Delivery.created_at.desc()).all()
    deliveries_data = []
    for d in deliveries:
        deliveries_data.append({
            'id': d.id,
            'address': d.address,
            'city': d.city,
            'notes': d.notes,
            'lat': d.lat,
            'lon': d.lon,
            'delivered': bool(d.delivered)
        })
    session.close()
    return render_template('dashboard.html', deliveries=deliveries_data, gmaps_key=GMAPS_KEY)

@app.route('/add_delivery', methods=['POST'])
@login_required
def add_delivery():
    address = request.form.get('address')
    city = request.form.get('city')
    notes = request.form.get('notes')
    session = Session()
    d = Delivery(address=address, city=city, notes=notes)
    session.add(d)
    session.commit()
    session.close()
    flash('Entrega adicionada', 'success')
    return redirect(url_for('dashboard'))

def geocode(addr):
    if gmaps:
        try:
            res = gmaps.geocode(addr)
            if res and len(res)>0:
                loc = res[0]['geometry']['location']
                return float(loc['lat']), float(loc['lng'])
        except Exception as e:
            print('Google geocode error', e)
    try:
        url = 'https://nominatim.openstreetmap.org/search'
        params = {'q': addr, 'format':'json', 'limit':1}
        headers = {'User-Agent':'OTIMIZADORDEROTAS-IA/railway'}
        r = requests.get(url, params=params, headers=headers, timeout=8)
        r.raise_for_status()
        data = r.json()
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        print('Nominatim error', e)
    return None, None

@app.route('/geocode/<int:id>', methods=['POST'])
@login_required
def geocode_delivery(id):
    session = Session()
    d = session.get(Delivery, id)
    if not d:
        session.close()
        return jsonify({'error':'Not found'}), 404
    lat, lon = geocode(d.address + (', ' + d.city if d.city else ''))
    if lat and lon:
        d.lat = lat
        d.lon = lon
        session.commit()
        session.close()
        return jsonify({'ok':True,'lat':lat,'lon':lon})
    session.close()
    return jsonify({'error':'geocode_failed'}), 500

@app.route('/api/deliveries')
@login_required
def api_deliveries():
    session = Session()
    ds = session.query(Delivery).order_by(Delivery.created_at.desc()).all()
    session.close()
    out = []
    for d in ds:
        out.append({'id':d.id,'address':d.address,'city':d.city,'notes':d.notes,'lat':d.lat,'lon':d.lon,'delivered':d.delivered})
    return jsonify(out)

def haversine(a,b):
    R=6371
    lat1,lon1 = math.radians(a[0]), math.radians(a[1])
    lat2,lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2-lat1
    dlon = lon2-lon1
    x = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R*2*math.asin(math.sqrt(x))

@app.route('/api/optimize', methods=['POST'])
@login_required
def api_optimize():
    payload = request.json or {}
    start = payload.get('start')
    ids = payload.get('ids', [])
    # default priority: time (mais rápido)
    priority = payload.get('priority','time')
    if not start or not ids:
        return jsonify({'error':'missing'}), 400
    session = Session()
    deliveries = [session.get(Delivery, i) for i in ids]
    session.close()
    for d in deliveries:
        if not d or d.lat is None or d.lon is None:
            return jsonify({'error':'all deliveries must have lat/lon'}), 400
    coords = [(start['lat'], start['lon'])] + [(d.lat,d.lon) for d in deliveries]
    n = len(coords)
    dist = [[0]*n for _ in range(n)]
    # try Google Distance Matrix for realistic travel times if available
    if gmaps:
        try:
            origins = coords
            destinations = coords
            resp = gmaps.distance_matrix(origins, destinations, mode='driving', units='metric')
            rows = resp.get('rows', [])
            if rows and len(rows)==len(origins):
                for i in range(n):
                    els = rows[i].get('elements', [])
                    for j in range(n):
                        if i==j: continue
                        if j < len(els) and els[j].get('status')=='OK':
                            # use duration (seconds) for time-priority
                            if priority == 'time':
                                dist[i][j] = int(els[j]['duration']['value'])
                            else:
                                dist[i][j] = int(els[j]['distance']['value'])
                        else:
                            dist[i][j] = int(haversine(coords[i],coords[j])*1000)
            else:
                raise Exception('incomplete rows')
        except Exception as e:
            print('Google matrix failed, fallback to haversine', e)
            for i in range(n):
                for j in range(n):
                    if i==j: continue
                    dist[i][j] = int(haversine(coords[i],coords[j])*1000)
    else:
        for i in range(n):
            for j in range(n):
                if i==j: continue
                # when prioritizing time we use haversine distance as proxy (meters)
                dist[i][j] = int(haversine(coords[i],coords[j])*1000)

    # OR-Tools routing (minimize the cost computed above)
    manager = pywrapcp.RoutingIndexManager(n,1,0)
    routing = pywrapcp.RoutingModel(manager)
    def dc(i,j):
        return dist[manager.IndexToNode(i)][manager.IndexToNode(j)]
    transit_idx = routing.RegisterTransitCallback(dc)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)
    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    sol = routing.SolveWithParameters(search)
    if not sol:
        return jsonify({'error':'no_solution'}), 500
    index = routing.Start(0)
    order = []
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if node!=0:
            order.append(ids[node-1])
        index = sol.Value(routing.NextVar(index))
    return jsonify({'order':order})

    # (end of optimize)

@app.route('/open_waze/<int:id>')
@login_required
def open_waze(id):
    session = Session()
    d = session.get(Delivery, id)
    session.close()
    if not d:
        return redirect(url_for('dashboard'))
    if d.lat and d.lon:
        link = f'https://waze.com/ul?ll={d.lat},{d.lon}&navigate=yes'
    else:
        link = f'https://waze.com/ul?q={quote_plus(d.address)}&navigate=yes'
    return redirect(link)

@app.route('/open_maps/<int:id>')
@login_required
def open_maps(id):
    session = Session()
    d = session.get(Delivery, id)
    session.close()
    if not d:
        return redirect(url_for('dashboard'))
    if d.lat and d.lon:
        link = f'https://www.google.com/maps/dir/?api=1&destination={d.lat},{d.lon}'
    else:
        link = f'https://www.google.com/maps/search/{quote_plus(d.address)}'
    return redirect(link)

@app.route('/export_pdf')
@login_required
def export_pdf():
    session = Session()
    deliveries = session.query(Delivery).order_by(Delivery.created_at.desc()).all()
    session.close()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.drawString(40, 800, 'OTIMIZADORDEROTAS-IA - Relatório de Entregas')
    y = 760
    for d in deliveries:
        c.drawString(40, y, f"#{d.id} - {d.address} ({d.city}) - lat:{d.lat} lon:{d.lon}")
        y -= 14
        if y < 60:
            c.showPage(); y = 800
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='relatorio_entregas.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
