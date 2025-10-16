from flask import Blueprint, render_template, request, session, redirect, url_for, flash, make_response
from app import db
from app.models import User
from flask_jwt_extended import create_access_token, unset_jwt_cookies
import secrets
from app.models import Score, User
from flask import jsonify
from datetime import datetime
from flask_login import current_user
from sqlalchemy import or_

bp = Blueprint('routes', __name__)

languages = {
    "am": "Amharic",
    "bax": "Bamun",
    "ewo": "Ewondo",
    "fmp": "Nufi",
    "gez": "Geez"
}


@bp.route('/')
def home():
    lang = request.args.get("lang") or session.get("lang") or "gez"
    session["lang"] = lang
    csrf = _generate_csrf_token()
    is_auth = bool(current_user.is_authenticated or session.get('user_id'))
    return render_template('home.html', languages=languages, selected_lang=lang, title='Home', csrf_token=csrf, is_authenticated=is_auth)


def _generate_csrf_token():
    token = secrets.token_urlsafe(24)
    session['csrf_token'] = token
    return token


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated or session.get('user_id'):
        flash('You are already logged in.', 'info')
        return redirect(url_for('routes.home'))

    if request.method == 'GET':
        return render_template('login.html', csrf_token=_generate_csrf_token())

    flash('Login is not available here. Use the main login flow.', 'warning')
    return redirect(url_for('routes.login'))


@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated or session.get('user_id'):
        flash('You are already logged in.', 'info')
        return redirect(url_for('routes.home'))

    if request.method == 'GET':
        return render_template('signup.html', csrf_token=_generate_csrf_token())

    flash('Signup is not available here. Use the main signup flow.', 'warning')
    return redirect(url_for('routes.signup'))


@bp.route('/logout', methods=['POST'])
def logout():
    csrf = request.form.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        flash('Invalid CSRF token', 'danger')
        return redirect(url_for('routes.home'))
    session.pop('user_id', None)
    resp = make_response(redirect(url_for('routes.home')))
    unset_jwt_cookies(resp)
    flash('Logged out', 'info')
    return resp



@bp.route('/save-score', methods=['POST'])
def save_score():
    data = request.get_json() or {}
    csrf = data.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'not_authenticated'}), 401

    language_code = data.get('language')
    language = languages.get(language_code, language_code)
    wpm = data.get('wpm')
    accuracy = data.get('accuracy')

    try:
        wpm = int(wpm)
        accuracy = float(accuracy)
    except Exception:
        return jsonify({'error': 'invalid_data'}), 400

    score = Score(user_id=user_id, language=language, wpm=wpm, accuracy=accuracy)
    db.session.add(score)
    db.session.commit()

    return jsonify({'ok': True, 'score_id': score.id, 'created_at': score.created_at.isoformat()}), 201



@bp.route('/rankings')
def rankings():
    lang_code = request.args.get('lang') or session.get('lang') or 'gez'
    lang_name = languages.get(lang_code, lang_code)
    print(lang_name)
    rows = (
        db.session.query(Score, User.username)
        .outerjoin(User, User.id == Score.user_id)
        .filter(or_(Score.language == lang_name, Score.language == lang_code))
        .order_by(Score.wpm.desc(), Score.accuracy.desc())
        .limit(10)
        .all()
    )
    
    

    data = []
    for score, username in rows:
        display_name = username or f'User {score.user_id}'
        data.append({
            'username': display_name,
            'language': score.language,
            'wpm': score.wpm,
            'accuracy': score.accuracy,
            'created_at': score.created_at.isoformat()
        })
        
    print(data)

    return jsonify(data)