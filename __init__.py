import os
from distutils.util import strtobool

from flask import Flask
from flask_mail import Mail
from dotenv import load_dotenv
from pymongo import MongoClient

from interface.routes import pages

load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config["MONGODB_URI"] = os.environ.get("MONGODB_URI")
    app.config["SECRET_KEY"] = os.environ.get("secret_key")
    app.secret_key = os.environ.get("secret_key")

    # Configure mail server
    app.config['MAIL_SERVER'] = os.environ.get("MAIL_SERVER")
    app.config['MAIL_PORT'] = os.environ.get("MAIL_PORT")
    app.config['MAIL_USERNAME'] = os.environ.get("MAIL_USERNAME")
    app.config['MAIL_PASSWORD'] = os.environ.get("MAIL_PASSWORD")
    app.config['MAIL_USE_TLS'] = bool(strtobool(os.environ.get("MAIL_USE_TLS", 'True')))
    app.config['MAIL_USE_SSL'] = bool(strtobool(os.environ.get("MAIL_USE_SSL", 'False')))
    mail = Mail(app)
    mail.init_app(app)
    
    # Configure upload file path flask
    UPLOAD_PATH = os.environ.get("UPLOAD_PATH")
    
    upload_folder = os.getcwd() + '/' + str(UPLOAD_PATH)
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
    app.config['UPLOAD_FOLDER'] = UPLOAD_PATH
    
    # Connect database 
    client = MongoClient(app.config["MONGODB_URI"])    
    app.db = client.get_database('SaxonQ_Web')
    app.register_blueprint(pages)
    return app