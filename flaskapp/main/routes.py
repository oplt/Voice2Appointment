from flask import render_template, request, Blueprint, jsonify


main = Blueprint('main', __name__)


@main.route("/")
@main.route("/home")
def home():
    return render_template('home.html')

