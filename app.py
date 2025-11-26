from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change this for production
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

# --- Users ---
USERS = {
    "matti": "9002",
    "max": "2010"
}

# --- Login required decorator ---
def login_required(f):
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# --- Login page ---
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

@app.route('/wipe_data', methods=['POST'])
@login_required
def wipe_data():
    confirm = request.form.get("confirm")
    if confirm == "YES":
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("DELETE FROM sales")
        c.execute("DELETE FROM purchases")
        conn.commit()
        conn.close()
        return redirect(url_for('inventory'))
    else:
        return redirect(url_for('inventory'))