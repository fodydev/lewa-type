import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_kEY') or 'dev_secret_key'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///lewa-type.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False