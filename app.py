from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
import random
import string
from textblob import TextBlob

app = Flask(__name__)
app.secret_key = "shield_final_version_ultra"

# RESTORED: ALL 100 RED FLAG WORDS FOR ML ANALYSIS
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

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    # Ensure tables match our 5-column logic
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, shield_id TEXT, category TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ratings 
                 (helper_id TEXT, username TEXT, rating INTEGER, review TEXT, risk_status TEXT)''')
    conn.commit()
    conn.close()

init_db()

def analyze_risk(review_text, stars):
    review_text = review_text.lower()
    sentiment = TextBlob(review_text).sentiment.polarity
    # AI logic: If star rating is low OR red flag word found OR sentiment is negative
    if any(word in review_text for word in RED_FLAGS) or sentiment < -0.3 or stars <= 2:
        return "High Risk"
    elif stars == 3:
        return "Suspicious"
    return "Verified Safe"

@app.route('/')
def index():
    return render_template('index.html', mode="login")

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form.get('username').lower().strip()
    password = request.form.get('password')
    role = request.form.get('role')
    category = request.form.get('category', 'N/A')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        # Generate permanent ID for workers
        sid = "SH-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4)) if role == 'worker' else None
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", (username, password, role, sid, category))
        conn.commit()
        return render_template('index.html', success="Signup successful! Please Sign In.", mode="login")
    except:
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
        session['user'], session['role'], session['sid'], session['cat'] = user[0], user[2], user[3], user[4]
        return redirect('/profile' if user[2] == 'worker' else '/dashboard')
    return render_template('index.html', error="Invalid Login.", mode="login")

@app.route('/dashboard')
def dashboard():
    if session.get('role') != 'client': return redirect('/')
    return render_template('dashboard.html', user=session['user'])

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
        return jsonify({"exists": True, "name": worker[0], "category": worker[1], "status": status, "rating": avg})
    return jsonify({"exists": False})

@app.route('/rate', methods=['POST'])
def rate():
    data = request.json
    risk = analyze_risk(data['review'], int(data['rating']))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO ratings VALUES (?, ?, ?, ?, ?)", (data['sid'].upper(), session['user'], data['rating'], data['review'], risk))
    conn.commit()
    conn.close()
    return jsonify({"message": f"Report Logged. AI Status: {risk}"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)