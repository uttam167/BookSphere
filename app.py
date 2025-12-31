from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.secret_key = "super-secret-key"

# ==========================
# DATABASE (SQLite)
# ==========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def execute(query, params=(), fetch=False, one=False):
    db = get_db()
    cur = db.cursor()
    cur.execute(query, params)
    data = None
    if fetch:
        data = cur.fetchone() if one else cur.fetchall()
    db.commit()
    db.close()
    return data

def init_db():
    
    
    db = get_db()
    cur = db.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'user',
        status TEXT DEFAULT 'pending'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        author TEXT,
        read_link TEXT,
        is_premium INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        book_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS premium_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        expiry_date DATE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        email TEXT,
        message TEXT,
        rating INTEGER
    )
    """)

    db.commit()
    db.close()

init_db()
def create_admin_if_not_exists():
    admin = execute(
        "SELECT id FROM users WHERE email=?",
        ("admin@gmail.com",),
        fetch=True,
        one=True
    )

    if not admin:
        execute(
            "INSERT INTO users (name,email,password,role,status) VALUES (?,?,?,?,?)",
            (
                "Admin",
                "admin@gmail.com",
                generate_password_hash("admin123"),
                "admin",
                "approved"
            )
        )
        print("✅ ADMIN AUTO-CREATED")

create_admin_if_not_exists()


# ==========================
# EMAIL CONFIG
# ==========================
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")

def send_feedback_email(name, email, message, rating):
    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_USER
        msg["To"] = GMAIL_USER
        msg["Subject"] = f"BooksSphere Feedback ({rating}/5)"
        body = f"From: {name}\nEmail: {email}\nRating: {rating}\n\n{message}"
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASS)
        server.send_message(msg)
        server.quit()
    except:
        pass

# ==========================
# ROUTES
# ==========================
@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"]
    password = request.form["password"]

    user = execute(
        "SELECT * FROM users WHERE email=? AND status='approved'",
        (email,), fetch=True, one=True
    )

    if user and check_password_hash(user["password"], password):
        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role"]

        premium = execute(
            "SELECT * FROM premium_users WHERE user_id=? AND expiry_date >= date('now')",
            (user["id"],), fetch=True, one=True
        )
        session["is_premium"] = True if premium else False

        return redirect("/admin" if user["role"] == "admin" else "/dashboard")

    flash("❌ Invalid login or not approved")
    return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        if execute("SELECT id FROM users WHERE email=?", (email,), fetch=True, one=True):
            flash("❌ Email already exists")
            return redirect("/register")

        execute(
            "INSERT INTO users (name,email,password) VALUES (?,?,?)",
            (name, email, password)
        )
        flash("✅ Registered! Wait for admin approval")
        return redirect("/")

    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/")

    books_free = execute("SELECT * FROM books WHERE is_premium=0", fetch=True)
    books_premium = execute("SELECT * FROM books WHERE is_premium=1", fetch=True)

    favorites = execute("""
        SELECT b.* FROM books b
        JOIN favorites f ON b.id=f.book_id
        WHERE f.user_id=?
        ORDER BY f.created_at DESC
    """, (session["user_id"],), fetch=True)

    return render_template(
        "user_dashboard.html",
        books_free=books_free,
        books_premium=books_premium,
        favorites=favorites,
        user_name=session["name"],
        is_premium=session.get("is_premium", False)
    )

@app.route("/toggle-favorite/<int:book_id>")
def toggle_favorite(book_id):
    if "user_id" not in session:
        return redirect("/")

    fav = execute(
        "SELECT id FROM favorites WHERE user_id=? AND book_id=?",
        (session["user_id"], book_id), fetch=True, one=True
    )

    if fav:
        execute("DELETE FROM favorites WHERE id=?", (fav["id"],))
    else:
        execute(
            "INSERT INTO favorites (user_id,book_id) VALUES (?,?)",
            (session["user_id"], book_id)
        )
    return redirect("/dashboard")

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if "user_id" not in session:
        return redirect("/")

    if request.method == "POST":
        execute(
            "INSERT INTO feedback (user_id,name,email,message,rating) VALUES (?,?,?,?,?)",
            (
                session["user_id"],
                session["name"],
                request.form["email"],
                request.form["message"],
                int(request.form["rating"])
            )
        )
        send_feedback_email(
            session["name"],
            request.form["email"],
            request.form["message"],
            request.form["rating"]
        )
        flash("✅ Feedback sent")
        return redirect("/dashboard")

    return render_template("feedback.html")

# ==========================
# ADMIN
# ==========================
@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return redirect("/")

    users = execute("SELECT * FROM users WHERE status='pending'", fetch=True)
    books = execute("SELECT * FROM books", fetch=True)
    return render_template("admin_dashboard.html", users=users, books=books)

@app.route("/approve/<int:user_id>")
def approve_user(user_id):
    if session.get("role") == "admin":
        execute("UPDATE users SET status='approved' WHERE id=?", (user_id,))
    return redirect("/admin")

@app.route("/add-book", methods=["POST"])
def add_book():
    if session.get("role") == "admin":
        execute(
            "INSERT INTO books (title,author,read_link) VALUES (?,?,?)",
            (
                request.form["title"],
                request.form["author"],
                request.form["link"]
            )
        )
    return redirect("/admin")
@app.route("/admin/users")
def admin_users():
    if session.get("role") != "admin":
        return redirect("/")

    users = execute(
        "SELECT id, name, email, role, status FROM users ORDER BY id DESC",
        fetch=True
    )

    return render_template("admin_users.html", users=users)


@app.route("/toggle-premium/<int:book_id>/<int:status>")
def toggle_premium(book_id, status):
    if session.get("role") == "admin":
        execute("UPDATE books SET is_premium=? WHERE id=?", (status, book_id))
    return redirect("/admin")
@app.route("/favorites")
def favorites():
    if "user_id" not in session:
        return redirect("/")

    favorites = execute("""
        SELECT b.* FROM books b
        JOIN favorites f ON b.id = f.book_id
        WHERE f.user_id=?
        ORDER BY f.created_at DESC
    """, (session["user_id"],), fetch=True)

    return render_template(
        "favorites.html",
        favorites=favorites,
        user_name=session["name"]
    )
@app.route("/read-books")
def read_books():
    if "user_id" not in session:
        return redirect("/")

    books = execute("SELECT * FROM books ORDER BY title", fetch=True)
    return render_template("read_books.html", books=books)
@app.route("/payment")
def payment():
    if "user_id" not in session:
        return redirect("/")
    return render_template("payment.html")
@app.route("/read/<int:book_id>")
def read_book(book_id):
    if "user_id" not in session:
        return redirect("/")

    book = execute(
        "SELECT * FROM books WHERE id=?",
        (book_id,), fetch=True, one=True
    )

    if not book:
        flash("❌ Book not found")
        return redirect("/dashboard")

    if book["is_premium"] == 1 and not session.get("is_premium"):
        flash("🔒 Premium required")
        return redirect("/payment")

    return redirect(book["read_link"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ==========================
# RUN
# ==========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

