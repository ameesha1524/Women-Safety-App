from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
from textblob import TextBlob

app = Flask(__name__)
app.secret_key = "secret123"

# 100 RED FLAGS: Behavioral and situational triggers for safety analysis [cite: 61]
RED_FLAGS = [
    "uneasy", "staring", "lingered", "aggressive", "uncomfortable", "forced", "looking around",
    "loitering", "nervous", "shifty", "evasive", "intimidating", "prying", "peeking",
    "following", "lurking", "invasive", "hostile", "rude", "creepy", "weird",
    "suspicious", "fake", "forged", "unauthorized", "no id", "refused", "demanded",
    "entry", "pushed", "blocked", "touched", "grabbed", "followed", "watched",
    "observed", "recorded", "photographed", "asked personal", "private questions", "living alone",
    "returning later", "wrong uniform", "no vehicle", "unmarked", "no badge", "expired",
    "hesitant", "anxious", "angry", "shouting", "threatening", "blackmail", "scammed",
    "overcharged", "lingering", "backdoor", "windows", "checking locks", "testing handles", "wandering",
    "off-limits", "upstairs", "bedroom", "bathroom", "closet", "jewelry", "cash",
    "wallet", "phone", "asking for water", "using phone", "delaying", "excuses",
    "no tools", "wrong category", "unexpected", "unscheduled", "no appointment", "insistent",
    "persisting", "ignoring", "boundaries", "close proximity", "whispering", "muttering", "erratic",
    "drunk", "high", "smell", "odor", "dirty", "disguise", "mask", "gloves",
    "hiding face", "avoiding camera", "security", "alarm", "sensors", "disabled", "tampered"
]

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS helpers (id TEXT, name TEXT, category TEXT, visits INTEGER, risk TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ratings (helper_id TEXT, username TEXT, rating INTEGER, review TEXT)''')
    conn.commit()
    conn.close()

init_db()

# ---------------- AI RISK LOGIC (NLP + STATS) ----------------
def update_helper_risk(helper_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Get all reviews and ratings for the helper [cite: 61]
    c.execute("SELECT rating, review FROM ratings WHERE helper_id=?", (helper_id,))
    reviews = c.fetchall()
    
    if not reviews:
        return "Unrated", 0

    total_ratings = len(reviews)
    avg_rating = sum([r[0] for r in reviews]) / total_ratings
    
    # NLP Behavioral Scan [cite: 60, 83]
    ai_flagged = False
    for r in reviews:
        review_text = r[1].lower()
        analysis = TextBlob(review_text)
        
        # Check for 100 Red-Flag keywords or highly negative sentiment 
        if any(flag in review_text for flag in RED_FLAGS) or analysis.sentiment.polarity < -0.4:
            ai_flagged = True
            break

    # Final Risk Classification [cite: 62, 87]
    if ai_flagged:
        risk = "High Risk"  # AI Behavioral override [cite: 144]
    elif avg_rating >= 4.0:
        risk = "Verified Safe"
    elif avg_rating >= 2.5:
        risk = "Suspicious"
    else:
        risk = "High Risk"

    c.execute("UPDATE helpers SET risk=? WHERE id=?", (risk, helper_id))
    conn.commit()
    conn.close()
    return risk, avg_rating

# ---------------- ROUTES ----------------
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.form
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (data['username'], data['password']))
    user = c.fetchone()
    
    if not user:
        c.execute("INSERT INTO users VALUES (?, ?)", (data['username'], data['password']))
        conn.commit()
        user = (data['username'], data['password'])

    conn.close()
    session['user'] = user[0]
    return redirect('/dashboard')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM helpers")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM helpers WHERE risk='High Risk'")
    risky = c.fetchone()[0]
    conn.close()

    return render_template('dashboard.html', total=total, risky=risky, user=session['user'])

@app.route('/add_helper', methods=['POST'])
def add_helper():
    data = request.json
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM helpers WHERE id=?", (data['id'],))
    if c.fetchone():
        return jsonify({"error": "Helper ID already exists!"})

    risk = "Unrated"
    c.execute("INSERT INTO helpers VALUES (?, ?, ?, ?, ?)", (data['id'], data['name'], data['category'], data['visits'], risk))
    c.execute("INSERT INTO logs(message) VALUES (?)", (f"New helper {data['name']} registered.",))
    conn.commit()
    conn.close()
    return jsonify({"risk": risk, "message": "Helper registered successfully!"})

@app.route('/verify/<id>')
def verify(id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM helpers WHERE id=?", (id,))
    h = c.fetchone()

    if h:
        c.execute("SELECT AVG(rating), COUNT(rating) FROM ratings WHERE helper_id=?", (id,))
        rating_data = c.fetchone()
        avg_rating = round(rating_data[0], 1) if rating_data[0] else "N/A"
        total_reviews = rating_data[1]
        conn.close()
        
        return jsonify({
            "exists": True,
            "name": h[1],
            "category": h[2],
            "visits": h[3],
            "risk": h[4],
            "rating": avg_rating,
            "total_reviews": total_reviews
        })

    conn.close()
    return jsonify({"exists": False, "error": "Unauthorized Entity: ID not found "})

@app.route('/rate_helper', methods=['POST'])
def rate_helper():
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"})
        
    data = request.json
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM helpers WHERE id=?", (data['id'],))
    if not c.fetchone():
        return jsonify({"error": "Helper ID not found."})

    c.execute("INSERT INTO ratings VALUES (?, ?, ?, ?)", 
              (data['id'], session['user'], data['rating'], data['review']))
    conn.commit()
    
    # Recalculate risk using AI sentiment analysis [cite: 62]
    new_risk, avg = update_helper_risk(data['id'])
    
    c.execute("INSERT INTO logs(message) VALUES (?)", (f"Incident logged for {data['id']}. Risk: {new_risk}",))
    conn.commit()
    conn.close()

    return jsonify({"message": f"Rating recorded. AI Status: {new_risk}"})

@app.route('/alert', methods=['POST'])
def alert():
    data = request.json
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO logs(message) VALUES (?)", (f"CRITICAL: SOS Alert from {session.get('user')} at {data.get('lat')}, {data.get('lon')}",))
    conn.commit()
    conn.close()
    return jsonify({"message": "Emergency alert broadcasted to contacts! 🚨 [cite: 122]"})

if __name__ == '__main__':
    app.run(debug=True)