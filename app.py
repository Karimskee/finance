from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd
from datetime import datetime

import os

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, "finance.db")

db = SQL(f"sqlite:///{db_path}")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get user bought stocks
    stocks = db.execute(
        "SELECT symbol, shares FROM stocks WHERE user_id = ?",
        session["user_id"]
    )

    # Group transactions by stock_symbol
    balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
    grand_total = balance

    # Filter stocks
    for stock in stocks:
        price = lookup(stock["symbol"])["price"]
        stock["price"] = price
        stock["total"] = stock["shares"] * price

        grand_total += stock["total"]

    return render_template("index.html", stocks=stocks, balance=balance, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        return render_template("buy.html")

    # User reached route via POST (as by submitting a form via POST)
    symbol = request.form.get("symbol")
    shares = request.form.get("shares")

    # Search for stock
    result = lookup(symbol)

    # If no such stock
    if not result:
        return apology("Stock not found.")

    # Retrieve stock information
    name = result["name"]
    price = result["price"]
    symbol = result["symbol"]

    # Validate the value of shares
    if shares.isdigit():
        shares = int(shares)

        if shares < 1:
            return apology("Shares must be a positive integer.")
    else:
        return apology("Shares must be a positive integer, not a string.")

    # Amount to pay for the shares
    to_pay = shares * price

    # Check user balance
    balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    # If balance is not sufficient
    if balance < to_pay:
        return apology("Your balance is not sufficient :(")

    # Update stocks
    user_stocks = db.execute("SELECT * FROM stocks WHERE symbol = ? AND user_id = ?",
                             symbol, session["user_id"])

    if len(user_stocks) >= 1:
        bought_shares = db.execute(
            "SELECT shares FROM stocks WHERE symbol = ? AND user_id = ?",
            symbol, session["user_id"])[0]["shares"]

        db.execute("UPDATE stocks SET shares = ? WHERE symbol = ? AND user_id = ?",
                   bought_shares + shares, symbol, session["user_id"])
    else:
        db.execute("INSERT INTO stocks (user_id, symbol, shares) VALUES (?, ?, ?)",
                   session["user_id"], symbol, shares)

    # Update user balance
    db.execute("UPDATE users SET cash = ? WHERE id = ?",
               balance - to_pay,
               session["user_id"])

    # Add transaction
    db.execute("INSERT INTO transactions (user_id, symbol, shares, amount, time, state)" +
               "VALUES (?, ?, ?, ?, ?, ?)",
               session["user_id"],
               symbol,
               shares,
               to_pay,
               datetime.now(),
               "bought")

    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    user_id = session["user_id"]

    history = db.execute(
        "SELECT symbol, state, shares, amount, time FROM transactions WHERE user_id = ?",
        user_id)

    for row in history:
        row["amount"] = usd(row["amount"])

    if len(history) == 0:
        history = [{"symbol": "N/A", "state": "N/A", "shares": "N/A",
                    "amount": "N/A", "time": "N/A"}]

    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        return render_template("quote.html")

    # User reached route via POST (as by submitting a form via POST)

    # Get information from the HTML form
    symbol = request.form.get("symbol")

    # Blank input checking
    if not symbol:
        return apology("Missing input.")

    # Search for stock
    result = lookup(symbol)

    if not result:
        return apology("Stock not found.")

    # Retrieve stock information
    name = result["name"]
    price = result["price"]
    symbol = result["symbol"]

    return render_template("quoted.html", name=name, symbol=symbol, price=usd(price))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        return render_template("register.html")

    # User reached route via POST (as by submitting a form via POST)

    # Get information from the HTML form
    username = request.form.get("username")
    password = request.form.get("password")
    confirmation = request.form.get("confirmation")

    # Blank input checking
    if not username or not password or not confirmation:
        return apology("Missing input.")

    # Password and confirmation password not matching
    if password != confirmation:
        return apology("Password and password confirmation don't match.")

    # Inserting user data into the database
    try:
        db.execute("INSERT INTO users (username, hash) values (?, ?)",
                   username, generate_password_hash(password))
    except ValueError:
        return apology(f"User \"{username}\" is already registered.")

    session["user_id"] = db.execute("SELECT id FROM users WHERE username = ?", username)[0]["id"]

    return render_template("quote.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        stocks = db.execute("SELECT symbol, shares FROM stocks WHERE user_id = ?",
                            session["user_id"])

        return render_template("sell.html", stocks=stocks)

    # User reached route via POST (as by submitting a form via POST)
    symbol = request.form.get("symbol")
    shares = request.form.get("shares")

    if not symbol or not shares:
        return apology("Missing input.")

    # Validate the value of shares
    if shares.isdigit():
        shares = int(shares)

        if shares < 1:
            return apology("Shares must be a positive integer.")
    else:
        return apology("Shares must be a positive integer, not a string.")

    # If no such stock
    lookup_res = lookup(symbol)
    if not lookup_res:
        return apology("Stock not found.")

    price = lookup_res["price"]

    bought_shares = db.execute("SELECT shares FROM stocks WHERE symbol = ? AND user_id = ?",
                               symbol, session["user_id"])

    if not bought_shares:
        return apology("No bought stocks found for this company.")

    bought_shares = bought_shares[0]["shares"]

    if shares > bought_shares:
        return apology("Not enough shares to sell.")

    # Update user stocks
    if bought_shares - shares == 0:
        db.execute("DELETE FROM stocks WHERE symbol = ? AND user_id = ?",
                   symbol, session["user_id"])
    else:
        db.execute("UPDATE stocks SET shares = ? WHERE symbol = ? AND user_id = ?",
                   bought_shares - shares, symbol, session["user_id"])

    # Update user balance
    balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    db.execute("UPDATE users SET cash = ? WHERE id = ?",
               balance + shares * price,
               session["user_id"])

    # Add transaction
    db.execute("INSERT INTO transactions (user_id, symbol, shares, amount, time, state)" +
               "VALUES (?, ?, ?, ?, ?, ?)",
               session["user_id"],
               symbol,
               shares,
               shares * price,
               datetime.now(),
               "sold")

    return redirect("/")


@app.route("/change_pass", methods=["GET", "POST"])
@login_required
def change_pass():

    # If entered via navigation
    if request.method == "GET":
        return render_template("change_pass.html")

    # If entered via form submittion
    old_pass = request.form.get("old_pass")
    new_pass = request.form.get("new_pass")
    confirm_pass = request.form.get("confirm_pass")

    # Validate input
    if not old_pass or not new_pass or not confirm_pass:
        return apology("Missing input.")

    if new_pass != confirm_pass:
        return apology("New password and confirmation password don't match.")

    user_pass = db.execute("SELECT hash FROM users WHERE id = ?", session["user_id"])[0]["hash"]

    if not check_password_hash(user_pass, old_pass):
        return apology("Wrong password.")

    db.execute("UPDATE users SET hash = ? WHERE id = ?",
               generate_password_hash(new_pass), session["user_id"])

    return redirect("/login")
