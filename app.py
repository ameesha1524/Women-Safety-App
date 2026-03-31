from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3, random, string, json, math, pyotp
from textblob import TextBlob
from datetime import datetime

app = Flask(__name__)
app.secret_key = "shield_final_tactical_v4"

# --- AI CONFIG: Load Red Flags ---
try:
    with open('red_flags.json', 'r') as file:
        flag_categories = json.load(file)
        RED_FLAGS = [word for category in flag_categories.values() for word in category]
except FileNotFoundError:
    RED_FLAGS = ["uncomfortable", "aggressive", "creepy", "fake id"]

# --- MATH: HAVERSINE FORMULA ---
def calculate_distance(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return c * 6371 

def analyze_risk(review_text, stars):
    review_text = review_text.lower()
    sentiment = TextBlob(review_text).sentiment.polarity
    if any(word in review_text for word in RED_FLAGS) or sentiment < -0.3 or stars <= 2:
        return "High Risk"
    return "Verified Safe" if stars >= 4 else "Suspicious"

# --- DATABASE INITIALIZATION ---
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, 
                  shield_id TEXT, category TEXT, house_code TEXT, otp_secret TEXT)''')
    c.execute('CREATE TABLE IF NOT EXISTS ratings (helper_id TEXT, username TEXT, rating INTEGER, review TEXT, risk_status TEXT, latitude REAL, longitude REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, house_code TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS sessions (username TEXT, house_code TEXT, end_time DATETIME, status TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- NEW: HOUSEHOLD & MAP ROUTES (Fixes 404 Errors) ---

@app.route('/household')
def household():
    if 'user' not in session: return redirect('/')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    # Fetch all members sharing the same house code
    c.execute("SELECT username, role FROM users WHERE house_code=?", (session['house_code'],))
    members = c.fetchall()
    conn.close()
    return render_template('household.html', members=members, house_code=session['house_code'])

@app.route('/map')
def map_page():
    if session.get('role') != 'client': return redirect('/')
    return render_template('map.html')

@app.route('/api/v1/community_map')
def community_map():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT latitude, longitude, risk_status FROM ratings WHERE latitude != 0")
    data = c.fetchall()
    conn.close()
    return jsonify([[r[0], r[1], (1.0 if r[2] == 'High Risk' else 0.2)] for r in data])

# --- DYNAMIC TOKEN APIs ---

@app.route('/api/v1/generate_token')
def generate_token():
    if session.get('role') != 'worker': return jsonify({"error": "Unauthorized"}), 403
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT otp_secret FROM users WHERE username=?", (session['user'],))
    res = c.fetchone()
    conn.close()
    if not res: return jsonify({"error": "User not found"}), 404
    totp = pyotp.TOTP(res[0], interval=60)
    return jsonify({"token": totp.now(), "sid": session['sid']})

@app.route('/api/v1/verify_token', methods=['POST'])
def verify_token():
    d = request.json
    sid = d.get('sid', '').upper().strip()
    token = d.get('token', '').strip()
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT otp_secret, username, category FROM users WHERE shield_id=?", (sid,))
    worker = c.fetchone()
    if not worker:
        conn.close()
        return jsonify({"status": "REJECTED", "message": "Invalid Shield ID"}), 404
    totp = pyotp.TOTP(worker[0], interval=60)
    if not totp.verify(token):
        conn.close()
        return jsonify({"status": "REJECTED", "message": "Token Expired/Invalid (Impersonation Risk)"}), 403
    c.execute("SELECT rating, risk_status FROM ratings WHERE helper_id=?", (sid,))
    revs = c.fetchall()
    conn.close()
    avg = round(sum([r[0] for r in revs])/len(revs), 1) if revs else 0.0
    is_high_risk = any(r[1] == "High Risk" for r in revs)
    return jsonify({
        "status": "VERIFIED",
        "name": worker[1].capitalize(),
        "category": worker[2],
        "safety": "High Risk" if is_high_risk else "Verified Safe",
        "avg_rating": avg
    })

# --- AUTHENTICATION ROUTES ---

@app.route('/')
def index():
    return render_template('index.html', mode="login")

@app.route('/signup', methods=['POST'])
def signup():
    u = request.form.get('username', '').lower().strip()
    p = request.form.get('password')
    r = request.form.get('role')
    cat = request.form.get('category', 'N/A')
    h = request.form.get('house_code', '').upper().strip()
    otp_secret = pyotp.random_base32()
    if r == 'client' and not h:
        h = "FAM-" + "".join(random.choices(string.ascii_uppercase, k=4))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        sid = "SH-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4)) if r == 'worker' else None
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)", (u, p, r, sid, cat, h, otp_secret))
        conn.commit()
        return render_template('index.html', success="Account Created!", mode="login")
    except sqlite3.IntegrityError:
        return render_template('index.html', error="Username taken!", mode="signup")
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    u, p = request.form.get('username', '').lower().strip(), request.form.get('password')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p))
    user = c.fetchone()
    conn.close()
    if user:
        session['user'], session['role'], session['sid'], session['cat'], session['house_code'] = user[0], user[2], user[3], user[4], user[5]
        return redirect('/profile' if user[2] == 'worker' else '/dashboard')
    return render_template('index.html', error="Invalid Login.", mode="login")

# --- DASHBOARD & PROFILE ---
@app.route('/dashboard')
def dashboard():
    if session.get('role') != 'client': return redirect('/')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT message FROM logs WHERE house_code=? ORDER BY id DESC LIMIT 5", (session['house_code'],))
    logs = c.fetchall()
    conn.close()
    return render_template('dashboard.html', house_code=session['house_code'], logs=logs)

@app.route('/profile')
def profile():
    if session.get('role') != 'worker': return redirect('/')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT rating, review, risk_status FROM ratings WHERE helper_id=?", (session['sid'],))
    revs = c.fetchall()
    total = len(revs)
    avg = round(sum([r[0] for r in revs])/total, 1) if total else 0
    conn.close()
    return render_template('profile.html', sid=session['sid'], cat=session['cat'], reviews=revs, avg=avg, total=total)

# --- DEAD MAN'S SWITCH APIs ---
@app.route('/api/v1/start_timer', methods=['POST'])
def start_timer():
    mins = int(request.json.get('minutes', 15))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE username=?", (session['user'],))
    c.execute("INSERT INTO sessions VALUES (?, ?, datetime('now', 'localtime', ?), 'ACTIVE')", 
              (session['user'], session['house_code'], f'+{mins} minutes'))
    conn.commit()
    return jsonify({"status": "Started"})

@app.route('/api/v1/stop_timer', methods=['POST'])
def stop_timer():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE username=?", (session['user'],))
    conn.commit()
    return jsonify({"status": "Stopped"})

# --- WORKER SAFETY & STEALTH HANDOFF ---
@app.route('/worker/task')
def worker_task():
    if session.get('role') != 'worker': return redirect('/')
    return render_template('worker_task.html')

@app.route('/api/v1/secure_delivery_info', methods=['POST'])
def secure_info():
    d = request.json
    dist = calculate_distance(d['worker_lat'], d['worker_lng'], 12.9716, 79.1594)
    if dist <= 0.05:
        return jsonify({"status": "UNLOCKED", "address": "Apartment 402, Block B, Tulip Heights", "entry_code": "9921", "message": "Arrived. Precise data revealed."})
    return jsonify({"status": "LOCKED", "address": "REDACTED", "message": f"Too far ({round(dist, 2)}km). Move closer."})

@app.route('/rate', methods=['POST'])
def rate():
    d = request.json
    risk = analyze_risk(d['review'], int(d['rating']))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO ratings VALUES (?, ?, ?, ?, ?, ?, ?)", (d['sid'].upper(), session['user'], d['rating'], d['review'], risk, d.get('lat', 0), d.get('lng', 0)))
    c.execute("INSERT INTO logs (house_code, message) VALUES (?, ?)", (session['house_code'], f"{session['user']} reported {d['sid'].upper()} ({risk})"))
    conn.commit()
    conn.close()
    return jsonify({"message": f"Logged. AI Result: {risk}"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)