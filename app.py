from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
import random
import string
import json
from textblob import TextBlob

app = Flask(__name__)
app.secret_key = "shield_final_version_ultra"

# Load Red Flags dynamically from the JSON file
try:
    with open('red_flags.json', 'r') as file:
        flag_categories = json.load(file)
        RED_FLAGS = [word for category in flag_categories.values() for word in category]
except FileNotFoundError:
    print("Warning: red_flags.json not found. Using default list.")
    RED_FLAGS = ["uncomfortable", "aggressive", "creepy", "fake id"]

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, shield_id TEXT, category TEXT, house_code TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ratings 
                 (helper_id TEXT, username TEXT, rating INTEGER, review TEXT, risk_status TEXT, latitude REAL, longitude REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, house_code TEXT, message TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# ---------------- AI RISK LOGIC ----------------
def analyze_risk(review_text, stars):
    review_text = review_text.lower()
    sentiment = TextBlob(review_text).sentiment.polarity
    if any(word in review_text for word in RED_FLAGS) or sentiment < -0.3 or stars <= 2:
        return "High Risk"
    elif stars == 3:
        return "Suspicious"
    return "Verified Safe"

# ---------------- WEB ROUTES ----------------
@app.route('/')
def index():
    return render_template('index.html', mode="login")

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form.get('username').lower().strip()
    password = request.form.get('password')
    role = request.form.get('role')
    category = request.form.get('category', 'N/A')
    
    house_code = request.form.get('house_code', '').upper().strip()
    if role == 'client' and not house_code:
        house_code = "FAM-" + "".join(random.choices(string.ascii_uppercase, k=4))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        sid = "SH-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4)) if role == 'worker' else None
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", (username, password, role, sid, category, house_code))
        conn.commit()
        success_msg = f"Account created! Your Household Code is: {house_code}" if role == 'client' else "Worker Account Created!"
        return render_template('index.html', success=success_msg, mode="login")
    except sqlite3.IntegrityError:
        return render_template('index.html', error="Username taken!", mode="signup")
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username').lower().strip()
    password = request.form.get('password')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    user = c.fetchone()
    conn.close()
    
    if user:
        session['user'], session['role'], session['sid'], session['cat'], session['house_code'] = user[0], user[2], user[3], user[4], user[5]
        return redirect('/profile' if user[2] == 'worker' else '/dashboard')
    
    return render_template('index.html', error="Invalid Login.", mode="login")

@app.route('/dashboard')
def dashboard():
    if session.get('role') != 'client': return redirect('/')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT message FROM logs WHERE house_code=? ORDER BY id DESC LIMIT 5", (session.get('house_code'),))
    family_logs = c.fetchall()
    conn.close()
    return render_template('dashboard.html', user=session['user'], house_code=session.get('house_code'), logs=family_logs)

@app.route('/profile')
def profile():
    if session.get('role') != 'worker': return redirect('/')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT rating, review, risk_status FROM ratings WHERE helper_id=?", (session['sid'],))
    reviews = c.fetchall()
    avg = round(sum([r[0] for r in reviews])/len(reviews), 1) if reviews else 0
    conn.close()
    return render_template('profile.html', user=session['user'], sid=session['sid'], cat=session['cat'], reviews=reviews, avg=avg)

@app.route('/verify/<sid>')
def verify(sid):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT username, category FROM users WHERE shield_id=?", (sid.upper(),))
    worker = c.fetchone()
    if worker:
        c.execute("SELECT rating, review, risk_status FROM ratings WHERE helper_id=?", (sid.upper(),))
        ratings = c.fetchall()
        status = "Verified Safe"
        if any(r[2] == "High Risk" for r in ratings): status = "High Risk"
        avg = round(sum([r[0] for r in ratings])/len(ratings), 1) if ratings else 0
        
        if session.get('house_code'):
            c.execute("INSERT INTO logs (house_code, message) VALUES (?, ?)", 
                      (session['house_code'], f"{session['user']} verified {worker[0]} ({status})"))
            conn.commit()
            
        return jsonify({"exists": True, "name": worker[0], "category": worker[1], "status": status, "rating": avg})
    return jsonify({"exists": False})

@app.route('/rate', methods=['POST'])
def rate():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    risk = analyze_risk(data['review'], int(data['rating']))
    lat = data.get('lat', 0.0)
    lng = data.get('lng', 0.0)
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO ratings VALUES (?, ?, ?, ?, ?, ?, ?)", 
              (data['sid'].upper(), session['user'], data['rating'], data['review'], risk, lat, lng))
    
    if session.get('house_code'):
        c.execute("INSERT INTO logs (house_code, message) VALUES (?, ?)", 
                  (session['house_code'], f"{session['user']} logged a report for {data['sid'].upper()}. Status: {risk}"))
    
    conn.commit()
    conn.close()
    return jsonify({"message": f"Report Logged. AI Status: {risk}"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------------- MAP & ENTERPRISE APIs ----------------
@app.route('/api/v1/community_map')
def community_map():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT latitude, longitude, risk_status FROM ratings WHERE latitude IS NOT NULL AND longitude IS NOT NULL")
    community_data = c.fetchall()
    conn.close()

    heatmap_points = []
    for row in community_data:
        lat, lng, risk = row
        if risk == 'High Risk': intensity = 1.0
        elif risk == 'Suspicious': intensity = 0.5
        else: intensity = 0.1
        heatmap_points.append([lat, lng, intensity])

    return jsonify(heatmap_points)

@app.route('/api/v1/analyze_fleet_review', methods=['POST'])
def api_analyze_review():
    api_key = request.headers.get('X-API-KEY')
    if api_key != "swiggy_test_key_123": 
        return jsonify({"error": "Unauthorized API Key"}), 401

    data = request.json
    worker_id = data.get('worker_id')
    review_text = data.get('review_text', '')
    stars = data.get('rating', 5)

    risk_status = analyze_risk(review_text, stars)
    triggered_flags = [word for word in RED_FLAGS if word in review_text.lower()]

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO ratings VALUES (?, ?, ?, ?, ?, NULL, NULL)", 
              (worker_id, "API_IMPORT", stars, review_text, risk_status))
    conn.commit()
    conn.close()

    return jsonify({
        "worker_id": worker_id,
        "ai_risk_assessment": risk_status,
        "flags_detected": triggered_flags,
        "action_recommended": "Suspend" if risk_status == "High Risk" else "None"
    }), 200

if __name__ == '__main__': 
    app.run(debug=True)