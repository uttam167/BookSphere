from flask import Flask, render_template, request, redirect, session, flash
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret")

# ==========================
# DATABASE
# ==========================
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
        sslmode="require"
    )

def execute(query, params=(), fetch=False, one=False):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, params)
    data = None
    if fetch:
        data = cur.fetchone() if one else cur.fetchall()
    conn.commit()
    cur.close()
    conn.close()
    return data

# ==========================
# INIT ADMIN (SAFE)
# ==========================
def create_admin():
    admin = execute(
        "SELECT id FROM users WHERE email=%s",
        ("admin@gmail.com",),
        fetch=True,
        one=True
    )
    if not admin:
        execute(
            """
            INSERT INTO users (name,email,password,role,status)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (
                "Admin",
                "admin@gmail.com",
                generate_password_hash("admin123"),
                "admin",
                "approved"
            )
        )

@app.route("/init-admin")
def init_admin():
    if request.args.get("key") != os.getenv("ADMIN_INIT_KEY"):
        return "Unauthorized", 403
    create_admin()
    return "Admin created"

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
        "SELECT * FROM users WHERE email=%s",
        (email,),
        fetch=True,
        one=True
    )

    if not user:
        flash("❌ User not found")
        return redirect("/")

    if user["status"] != "approved":
        flash("⏳ Admin approval pending")
        return redirect("/")

    if not check_password_hash(user["password"], password):
        flash("❌ Wrong password")
        return redirect("/")

    session["user_id"] = user["id"]
    session["name"] = user["name"]
    session["role"] = user["role"]

    try:
        premium = execute(
            "SELECT id FROM premium_users WHERE user_id=%s AND expiry_date >= CURRENT_DATE",
            (user["id"],),
            fetch=True,
            one=True
        )
        session["is_premium"] = True if premium else False
    except:
        session["is_premium"] = False

    return redirect("/admin" if user["role"] == "admin" else "/dashboard")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        exists = execute(
            "SELECT id FROM users WHERE email=%s",
            (email,),
            fetch=True,
            one=True
        )
        if exists:
            flash("❌ Email already exists")
            return redirect("/register")

        execute(
            "INSERT INTO users (name,email,password,status) VALUES (%s,%s,%s,'pending')",
            (name, email, password)
        )
        flash("✅ Registered! Admin approval required")
        return redirect("/")

    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/")

    books_free = execute(
        "SELECT * FROM books WHERE is_premium=false",
        fetch=True
    )
    books_premium = execute(
        "SELECT * FROM books WHERE is_premium=true",
        fetch=True
    )

    favorites = execute(
        """
        SELECT b.* FROM books b
        JOIN favorites f ON b.id=f.book_id
        WHERE f.user_id=%s
        """,
        (session["user_id"],),
        fetch=True
    )

    return render_template(
        "user_dashboard.html",
        books_free=books_free,
        books_premium=books_premium,
        favorites=favorites,
        user_name=session["name"],
        is_premium=session.get("is_premium", False)
    )

# ==========================
# ADMIN
# ==========================
@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return redirect("/")

    users = execute(
        "SELECT * FROM users WHERE status='pending'",
        fetch=True
    )
    books = execute("SELECT * FROM books", fetch=True)
    return render_template("admin_dashboard.html", users=users, books=books)

@app.route("/approve/<int:user_id>")
def approve_user(user_id):
    if session.get("role") == "admin":
        execute(
            "UPDATE users SET status='approved' WHERE id=%s",
            (user_id,)
        )
    return redirect("/admin")

@app.route("/add-book", methods=["POST"])
def add_book():
    if session.get("role") == "admin":
        execute(
            "INSERT INTO books (title,author,read_link) VALUES (%s,%s,%s)",
            (
                request.form["title"],
                request.form["author"],
                request.form["link"]
            )
        )
    return redirect("/admin")

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
