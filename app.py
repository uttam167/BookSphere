from flask import Flask, render_template, request, redirect, session, flash
import mysql.connector
import os
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "super-secret-key"

# GMAIL CONFIG
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")

print("🚀 BooksSphere PRO Starting...")

# DATABASE FUNCTIONS
def get_db():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = mysql.connector.connect(
                host="localhost", user="root", password="6299",
                database="booksphere", autocommit=True, connection_timeout=10
            )
            return conn
        except Error as e:
            if "Lock wait timeout" in str(e) and attempt < max_retries - 1:
                time.sleep(1)
            else:
                print(f"❌ DB Error: {e}")
                raise

def execute_query(query, params=None, fetch=False, commit=False):
    db = None
    cur = None
    try:
        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute(query, params or ())
        if fetch:
            return cur.fetchall() if "SELECT" in query.upper() else cur.fetchone()
        if commit:
            db.commit()
        return True
    except Error as e:
        if db: db.rollback()
        print(f"❌ Query Error: {e}")
        raise
    finally:
        if cur: cur.close()
        if db: db.close()

def is_favorite(user_id, book_id):
    try:
        return execute_query("SELECT id FROM favorites WHERE user_id=%s AND book_id=%s", (user_id, book_id), fetch=True)
    except:
        return None

def send_feedback_email(name, email, message, rating):
    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = GMAIL_USER
        msg['Subject'] = f"BooksSphere Feedback - {rating}/5"
        body = f"NEW FEEDBACK: {name} ({rating}/5): {message}"
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except:
        return False

# ROUTES - SAFE ERROR HANDLING
@app.route("/")
def home():
    try:
        return render_template("login.html")
    except:
        return "Login page missing! Create templates/login.html"

@app.route("/login", methods=["POST"])
def login():
    try:
        email = request.form["email"]
        password = request.form["password"]
        user = execute_query("SELECT * FROM users WHERE email=%s AND status='approved'", (email,), fetch=True)
        
        if user and check_password_hash(user[0]["password"], password):
            session["user_id"] = user[0]["id"]
            session["name"] = user[0]["name"]
            session["role"] = user[0]["role"]
            premium = execute_query("SELECT * FROM premium_users WHERE user_id=%s AND expiry_date >= CURDATE()", (user[0]["id"],), fetch=True)
            session["is_premium"] = premium is not None
            return redirect("/admin" if user[0]["role"] == "admin" else "/dashboard")
        flash("❌ Invalid login!")
    except Exception as e:
        print(f"Login error: {e}")
        flash("❌ Login failed!")
    return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():
    try:
        if request.method == "POST":
            name = request.form["name"]
            email = request.form["email"]
            password = generate_password_hash(request.form["password"])
            if not execute_query("SELECT id FROM users WHERE email=%s", (email,), fetch=True):
                execute_query("INSERT INTO users (name,email,password,role,status) VALUES (%s,%s,%s,'user','pending')", (name,email,password), commit=True)
                flash("✅ Registered! Wait for approval.")
            else:
                flash("❌ Email exists!")
            return redirect("/")
        return render_template("register.html")
    except:
        flash("❌ Registration failed!")
        return redirect("/")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session: 
        return redirect("/")
    try:
        books_free = execute_query("SELECT * FROM books WHERE is_premium=0 OR is_premium IS NULL ORDER BY title", fetch=True)
        books_premium = execute_query("SELECT * FROM books WHERE is_premium=1 ORDER BY title", fetch=True)
        favorites = execute_query("SELECT b.*, f.id as fav_id FROM books b LEFT JOIN favorites f ON b.id = f.book_id AND f.user_id=%s WHERE f.id IS NOT NULL ORDER BY f.created_at DESC LIMIT 5", (session["user_id"],), fetch=True) or []
        return render_template("user_dashboard.html", books_free=books_free or [], books_premium=books_premium or [], user_name=session.get("name", "User"), is_premium=session.get("is_premium", False), favorites=favorites)
    except:
        flash("Dashboard loading failed!")
        return redirect("/")
    

@app.route("/toggle-favorite/<int:book_id>")
def toggle_favorite(book_id):
    if "user_id" not in session: 
        return redirect("/")
    try:
        user_id = session["user_id"]
        if is_favorite(user_id, book_id):
            execute_query("DELETE FROM favorites WHERE user_id=%s AND book_id=%s", (user_id, book_id), commit=True)
            flash("❤️ Removed from favorites!")
        else:
            execute_query("INSERT IGNORE INTO favorites (user_id, book_id) VALUES (%s, %s)", (user_id, book_id), commit=True)
            flash("💖 Added to favorites!")
    except:
        flash("❌ Favorite action failed!")
    return redirect(request.referrer or "/dashboard")

@app.route("/favorites")
def favorites():
    if "user_id" not in session: 
        return redirect("/")
    try:
        favorites = execute_query("SELECT b.*, f.created_at FROM books b LEFT JOIN favorites f ON b.id = f.book_id WHERE f.user_id=%s ORDER BY f.created_at DESC", (session["user_id"],), fetch=True) or []
        return render_template("favorites.html", favorites=favorites, user_name=session.get("name", "User"))
    except:
        return render_template("favorites.html", favorites=[], user_name="User")

@app.route("/read-books")
def read_books():
    if "user_id" not in session: 
        return redirect("/")
    try:
        books = execute_query("SELECT * FROM books ORDER BY title", fetch=True) or []
        return render_template("read_books.html", books=books)
    except:
        flash("❌ Books not found!")
        return redirect("/dashboard")

@app.route("/payment")
def payment():
    if "user_id" not in session: 
        return redirect("/")
    try:
        return render_template("payment.html")
    except:
        flash("Payment page loading failed!")
        return redirect("/dashboard")

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if "user_id" not in session: 
        return redirect("/")
    try:
        if request.method == "POST":
            execute_query("INSERT IGNORE INTO feedback (user_id, name, email, message, rating) VALUES (%s,%s,%s,%s,%s)", 
                         (session["user_id"], session["name"], request.form["email"], request.form["message"], int(request.form.get("rating", 5))), commit=True)
            send_feedback_email(session["name"], request.form["email"], request.form["message"], int(request.form.get("rating", 5)))
            flash("✅ Feedback sent!")
            return redirect("/dashboard")
        return render_template("feedback.html")
    except:
        flash("❌ Feedback failed!")
        return redirect("/dashboard")

@app.route("/payment-success/<int:user_id>")
def payment_success(user_id):
    try:
        execute_query("INSERT IGNORE INTO premium_users (user_id, expiry_date) VALUES (%s, DATE_ADD(CURDATE(), INTERVAL 30 DAY))", (user_id,), commit=True)
        if "user_id" in session and session["user_id"] == user_id:
            session["is_premium"] = True
        flash("🎉 Premium activated!")
    except:
        flash("❌ Premium activation failed!")
    return redirect("/dashboard")

@app.route("/read/<int:book_id>")
def read_book(book_id):
    try:
        book = execute_query("SELECT * FROM books WHERE id=%s", (book_id,), fetch=True)
        if book and (not book[0]["is_premium"] or session.get("is_premium")):
            return redirect(book[0]["read_link"])
        flash("🔒 Premium required or book not found!")
    except:
        flash("❌ Book not found!")
    return redirect("/dashboard")

# ADMIN ROUTES
@app.route("/admin")
def admin():
    if "user_id" not in session or session["role"] != "admin": 
        return redirect("/")
    try:
        users = execute_query("SELECT * FROM users WHERE status='pending'", fetch=True) or []
        books = execute_query("SELECT * FROM books ORDER BY title", fetch=True) or []
        return render_template("admin_dashboard.html", users=users, books=books)
    except:
        flash("Admin dashboard failed!")
        return redirect("/")

@app.route("/approve/<int:user_id>")
def approve_user(user_id):
    if session.get("role") == "admin":
        execute_query("UPDATE users SET status='approved' WHERE id=%s", (user_id,), commit=True)
        flash("✅ User approved!")
    return redirect("/admin")

@app.route("/toggle-premium/<int:book_id>/<int:status>")
def toggle_premium(book_id, status):
    if session.get("role") == "admin":
        execute_query("UPDATE books SET is_premium=%s WHERE id=%s", (status, book_id), commit=True)
        flash(f"⭐ Premium {'enabled' if status else 'disabled'}!")
    return redirect("/admin")

@app.route("/add-book", methods=["POST"])
def add_book():
    if session.get("role") == "admin":
        try:
            execute_query("INSERT INTO books (title, author, read_link) VALUES (%s,%s,%s)", 
                         (request.form["title"], request.form["author"], request.form["link"]), commit=True)
            flash("📚 Book added!")
        except:
            flash("❌ Add book failed!")
    return redirect("/admin")

@app.route("/delete-book/<int:book_id>")
def delete_book(book_id):
    if session.get("role") == "admin":
        try:
            book = execute_query("SELECT title FROM books WHERE id=%s", (book_id,), fetch=True)
            if book:
                execute_query("DELETE FROM books WHERE id=%s", (book_id,), commit=True)
                flash(f"🗑️ '{book[0]['title']}' deleted!")
            else:
                flash("❌ Book not found!")
        except:
            flash("❌ Delete failed!")
    return redirect("/admin")

@app.route("/admin/users")
def admin_users():
    if "user_id" not in session or session["role"] != "admin":
        return redirect("/")

    try:
        users = execute_query(
            "SELECT id, name, email, role, status FROM users ORDER BY status='pending' DESC, id DESC",
            fetch=True
        ) or []

        pending_count = execute_query("SELECT COUNT(*) as count FROM users WHERE status='pending'", fetch=True)
        approved_count = execute_query("SELECT COUNT(*) as count FROM users WHERE status='approved'", fetch=True)
        
        return render_template("admin_users.html", 
                             users=users,
                             pending_count=pending_count[0]['count'] if pending_count else 0,
                             approved_count=approved_count[0]['count'] if approved_count else 0,
                             admin_id=session["user_id"])  # ← YE ADD HUA

    except Exception as e:
        print("Admin users error:", e)
        flash("❌ User list load nahi ho paayi")
        return redirect("/admin")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
