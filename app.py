from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
from webauthn import generate_registration_options, generate_authentication_options, verify_registration_response, verify_authentication_response
import os
import json

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change this to anything random
DATABASE = "inventory.db"

# --- Database setup ---
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT,
            item_sort TEXT,
            quantity INTEGER,
            price REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            quantity INTEGER,
            sale_price REAL,
            FOREIGN KEY(item_id) REFERENCES purchases(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

USERS = {
    "matti": {"password": "9002", "webauthn": None},
    "max": {"password": "2010", "webauthn": None}
}

def login_required(f):
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USERS and USERS[username] == password:
            session['user'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid username or password.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


@app.route("/webauthn/register_options", methods=["POST"])
def webauthn_register_options():
    username = request.json["username"]
    if username not in USERS:
        return jsonify({"error": "Unknown user"}), 400
    registration_options = generate_registration_options(
        rp_name="Inventory Tracker",
        user_id=username.encode(),
        user_name=username,
        challenge=os.urandom(32)
    )
    session["challenge"] = registration_options.challenge
    return jsonify(json.loads(registration_options.json()))

@app.route("/webauthn/register_response", methods=["POST"])
def webauthn_register_response():
    username = request.json["username"]
    credential = request.json["credential"]
    challenge = session.get("challenge")
    if not challenge:
        return jsonify({"error": "No challenge found"}), 400
    USERS[username]["webauthn"] = credential
    return jsonify({"status": "ok"})

@app.route("/webauthn/authenticate_options", methods=["POST"])
def webauthn_authenticate_options():
    username = request.json["username"]
    if username not in USERS or not USERS[username]["webauthn"]:
        return jsonify({"error": "No passkey registered"}), 400
    options = generate_authentication_options(
        rp_id="inventory-tracker.onrender.com",  # Replace with your Render domain
        challenge=os.urandom(32)
    )
    session["challenge"] = options.challenge
    return jsonify(json.loads(options.json()))

@app.route("/webauthn/authenticate_response", methods=["POST"])
def webauthn_authenticate_response():
    username = request.json["username"]
    credential = request.json["credential"]
    challenge = session.get("challenge")
    if not challenge:
        return jsonify({"error": "No challenge found"}), 400
    session["user"] = username
    return jsonify({"status": "ok"})

# --- Dashboard ---
@app.route('/')
@login_required
def index():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT SUM(quantity * price) FROM purchases")
    total_spent = c.fetchone()[0] or 0
    c.execute("SELECT SUM(quantity * sale_price) FROM sales")
    total_revenue = c.fetchone()[0] or 0
    c.execute("SELECT s.quantity, s.sale_price, p.price FROM sales s JOIN purchases p ON s.item_id = p.id")
    profit = sum([(row[1] - row[2]) * row[0] for row in c.fetchall()])
    conn.close()
    return render_template("index.html", total_spent=total_spent, total_revenue=total_revenue, profit=profit)

# --- Purchases ---
@app.route('/purchases', methods=['GET', 'POST'])
@login_required
def purchases():
    if request.method == 'POST':
        item_name = request.form['item_name']
        item_sort = request.form['item_sort']
        quantity = int(request.form['quantity'])
        price = float(request.form['price'])
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("SELECT id, quantity FROM purchases WHERE item_name=? AND item_sort=?", (item_name, item_sort))
        existing = c.fetchone()
        if existing:
            item_id, old_qty = existing
            new_qty = old_qty + quantity
            c.execute("UPDATE purchases SET quantity=? WHERE id=?", (new_qty, item_id))
        else:
            c.execute("INSERT INTO purchases (item_name, item_sort, quantity, price) VALUES (?, ?, ?, ?)",
                      (item_name, item_sort, quantity, price))
        conn.commit()
        conn.close()
        return redirect(url_for('purchases'))
    return render_template('purchases.html')

# --- Sales ---
@app.route('/sales', methods=['GET', 'POST'])
@login_required
def sales():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT p.id, p.item_name, p.item_sort,
               SUM(p.quantity) - IFNULL((SELECT SUM(s.quantity) FROM sales s WHERE s.item_id=p.id),0) AS stock
        FROM purchases p
        GROUP BY p.id, p.item_name, p.item_sort
        HAVING stock > 0
    ''')
    items = c.fetchall()
    if request.method == 'POST':
        item_id = int(request.form['item_id'])
        quantity = int(request.form['quantity'])
        sale_price = float(request.form['sale_price'])
        c.execute("INSERT INTO sales (item_id, quantity, sale_price) VALUES (?, ?, ?)",
                  (item_id, quantity, sale_price))
        conn.commit()
        conn.close()
        return redirect(url_for('sales'))
    conn.close()
    return render_template('sales.html', items=items)

# --- Inventory ---
@app.route('/inventory')
@login_required
def inventory():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT p.item_name, p.item_sort,
               SUM(p.quantity) - IFNULL((SELECT SUM(s.quantity) FROM sales s WHERE s.item_id=p.id),0) AS stock,
               p.price
        FROM purchases p
        GROUP BY p.item_name, p.item_sort, p.price
        HAVING stock > 0
    ''')
    stock = c.fetchall()
    conn.close()
    return render_template('inventory.html', stock=stock)

if __name__ == '__main__':
    app.run(debug=True)
