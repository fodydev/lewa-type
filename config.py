import os

class Config:
    # Prefer SECRET_KEY env var (note: case-insensitive fallback)
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.environ.get('SECRET_kEY') or 'dev_secret_key'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///lewa-type.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_TOKEN_LOCATION = ['cookies']
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_ACCESS_COOKIE_PATH = '/'
    JWT_REFRESH_COOKIE_PATH = '/token/refresh'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'dev_jwt_secret'