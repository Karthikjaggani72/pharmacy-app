
from flask import Flask, render_template, request, redirect, url_for
from datetime import date
import os

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form['username'] == "admin" and request.form['password'] == "admin":
            return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/master", methods=["GET", "POST"])
def master():
    if request.method == "POST":
        file = request.files["excel"]
        file.save(os.path.join("uploads", file.filename))
    return render_template("master_form.html")

@app.route("/pharmacy")
def pharmacy():
    return render_template("pharmacy_form.html", sale_date=date.today().isoformat())

if __name__ == "__main__":
    app.run(debug=True)
