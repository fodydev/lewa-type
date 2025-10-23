from flask import Blueprint, render_template, request, session, redirect, url_for, flash, make_response, Response, stream_with_context
from app import db
from app.models import User
from flask_jwt_extended import create_access_token, unset_jwt_cookies, set_access_cookies
import secrets
from app.models import Score, User, Competition, CompetitionParticipant, CompetitionInvite, CompetitionScore
import json
import time
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


def _generate_csrf_token():
    token = secrets.token_urlsafe(24)
    session['csrf_token'] = token
    return token


@bp.route('/')
def home():
    lang = request.args.get("lang") or session.get("lang") or "gez"
    session["lang"] = lang
    csrf = _generate_csrf_token()
    is_auth = bool(current_user.is_authenticated or session.get('user_id'))
    return render_template('home.html', languages=languages, selected_lang=lang, title='Home', csrf_token=csrf, is_authenticated=is_auth)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated or session.get('user_id'):
        flash('You are already logged in.', 'info')
        return redirect(url_for('routes.home'))

    if request.method == 'GET':
        return render_template('login.html', csrf_token=_generate_csrf_token())
    # POST: perform authentication
    form = request.form or {}
    csrf = form.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        flash('Invalid CSRF token', 'danger')
        return redirect(url_for('routes.login'))

    identifier = form.get('identifier', '').strip()
    password = form.get('password', '')
    if not identifier or not password:
        flash('Missing credentials', 'warning')
        return redirect(url_for('routes.login'))

    user = User.query.filter(or_(User.username == identifier, User.email == identifier)).first()
    if not user or not user.check_password(password):
        flash('Invalid username or password', 'danger')
        return redirect(url_for('routes.login'))

    # login success
    session['user_id'] = user.id
    access_token = create_access_token(identity=str(user.id))
    resp = make_response(redirect(url_for('routes.home')))
    set_access_cookies(resp, access_token)
    flash('Logged in', 'success')
    return resp


@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated or session.get('user_id'):
        flash('You are already logged in.', 'info')
        return redirect(url_for('routes.home'))

    if request.method == 'GET':
        return render_template('signup.html', csrf_token=_generate_csrf_token())
    # POST: create new user
    form = request.form or {}
    csrf = form.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        flash('Invalid CSRF token', 'danger')
        return redirect(url_for('routes.signup'))

    username = form.get('username', '').strip()
    email = form.get('email', '').strip().lower()
    password = form.get('password', '')

    if not username or not email or not password:
        flash('All fields are required', 'warning')
        return redirect(url_for('routes.signup'))

    # check uniqueness
    exists = User.query.filter((User.username == username) | (User.email == email)).first()
    if exists:
        flash('Username or email already exists', 'warning')
        return redirect(url_for('routes.signup'))

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    access_token = create_access_token(identity=str(user.id))
    resp = make_response(redirect(url_for('routes.home')))
    set_access_cookies(resp, access_token)
    flash('Account created and logged in', 'success')
    return resp


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


@bp.route('/competitions', methods=['GET'])
def competitions_page():
    # render list page
    csrf = _generate_csrf_token()
    return render_template('competitions.html', languages=languages, csrf_token=csrf)


@bp.route('/api/competitions')
def api_competitions():
    # Return public competitions plus those the user manages or participates in
    user_id = session.get('user_id')
    q = Competition.query.filter(Competition.is_public == True)
    if user_id:
        # include ones managed or joined
        managed = Competition.query.filter(Competition.manager_id == user_id)
        joined_ids = db.session.query(CompetitionParticipant.competition_id).filter(CompetitionParticipant.user_id == user_id).subquery()
        joined = Competition.query.filter(Competition.id.in_(joined_ids))
        q = q.union(managed, joined)

    comps = q.order_by(Competition.created_at.desc()).all()
    out = []
    for c in comps:
        out.append({'id': c.id, 'title': c.title, 'language': c.language, 'is_public': c.is_public})
    return jsonify(out)


@bp.route('/competitions/new')
def create_competition_page():
    if not (current_user.is_authenticated or session.get('user_id')):
        flash('You must be logged in to create competitions', 'warning')
        return redirect(url_for('routes.login'))
    return render_template('competition_create.html', languages=languages, csrf_token=_generate_csrf_token())


@bp.route('/competitions', methods=['POST'])
def create_competition():
    data = request.get_json() or {}
    csrf = data.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'not_authenticated'}), 401

    title = (data.get('title') or '').strip()
    lang_code = data.get('language')
    is_public = bool(data.get('is_public'))
    live_ranking = bool(data.get('live_ranking'))

    if not title or not lang_code:
        return jsonify({'error': 'missing_fields'}), 400

    comp = Competition(title=title, language=lang_code, is_public=is_public, live_ranking=live_ranking, manager_id=user_id)
    db.session.add(comp)
    db.session.commit()

    # add creator as participant
    part = CompetitionParticipant(competition_id=comp.id, user_id=user_id)
    db.session.add(part)
    db.session.commit()

    return jsonify({'ok': True, 'competition_id': comp.id}), 201


@bp.route('/competitions/<int:comp_id>/manage')
def manage_competition_page(comp_id):
    comp = Competition.query.get_or_404(comp_id)
    user_id = session.get('user_id')
    if not user_id or comp.manager_id != user_id:
        flash('You do not have permission to manage this competition', 'danger')
        return redirect(url_for('routes.competitions_page'))
    return render_template('competition_manage.html', comp_id=comp.id, csrf_token=_generate_csrf_token())


@bp.route('/competitions/<int:comp_id>/play')
def play_competition(comp_id):
    comp = Competition.query.get_or_404(comp_id)
    user_id = session.get('user_id')
    # if competition is private, require the user to be a participant or manager
    if not comp.is_public:
        if not user_id:
            flash('You must be logged in to join this competition', 'warning')
            return redirect(url_for('routes.login'))
        participant = CompetitionParticipant.query.filter_by(competition_id=comp.id, user_id=user_id).first()
        if not participant and comp.manager_id != user_id:
            flash('You must join this competition to play', 'warning')
            return redirect(url_for('routes.competitions_page'))

    # render play interface (typing area + live rankings)
    is_auth = bool(current_user.is_authenticated or session.get('user_id'))
    return render_template('competition_play.html', comp_id=comp.id, title=comp.title, language=comp.language, csrf_token=_generate_csrf_token(), is_authenticated=is_auth)


@bp.route('/api/competitions/<int:comp_id>/participants')
def api_competition_participants(comp_id):
    parts = (db.session.query(CompetitionParticipant, User.username)
             .join(User, User.id == CompetitionParticipant.user_id)
             .filter(CompetitionParticipant.competition_id == comp_id)
             .order_by(CompetitionParticipant.joined_at.asc())
             .all())
    out = []
    for p, username in parts:
        out.append({'id': p.user_id, 'username': username})
    return jsonify(out)


@bp.route('/competitions/<int:comp_id>/invite', methods=['POST'])
def create_invite(comp_id):
    comp = Competition.query.get_or_404(comp_id)
    user_id = session.get('user_id')
    if not user_id or comp.manager_id != user_id:
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json() or {}
    csrf = data.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    token = secrets.token_urlsafe(8)
    invite = CompetitionInvite(competition_id=comp.id, token=token, invited_by=user_id)
    db.session.add(invite)
    db.session.commit()
    return jsonify({'ok': True, 'invite_token': token})


@bp.route('/competitions/join', methods=['POST'])
def join_by_invite():
    data = request.get_json() or {}
    csrf = data.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'missing_token'}), 400
    invite = CompetitionInvite.query.filter_by(token=token).first()
    if not invite or not invite.is_valid():
        return jsonify({'error': 'invalid_invite'}), 400

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'not_authenticated'}), 401

    # already participant?
    exists = CompetitionParticipant.query.filter_by(competition_id=invite.competition_id, user_id=user_id).first()
    if exists:
        return jsonify({'ok': True, 'message': 'already_joined'})

    part = CompetitionParticipant(competition_id=invite.competition_id, user_id=user_id)
    invite.used = True
    db.session.add(part)
    db.session.add(invite)
    db.session.commit()
    return jsonify({'ok': True, 'competition_id': invite.competition_id})


@bp.route('/competitions/<int:comp_id>/submit-score', methods=['POST'])
def submit_competition_score(comp_id):
    data = request.get_json() or {}
    csrf = data.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'not_authenticated'}), 401

    # check participant
    comp = Competition.query.get_or_404(comp_id)
    participant = CompetitionParticipant.query.filter_by(competition_id=comp.id, user_id=user_id).first()
    print(participant)
    if not participant:
        return jsonify({'error': 'not_participant'}), 403

    try:
        wpm = int(data.get('wpm'))
        accuracy = float(data.get('accuracy'))
    except Exception:
        return jsonify({'error': 'invalid_data'}), 400

    cs = CompetitionScore(competition_id=comp.id, user_id=user_id, wpm=wpm, accuracy=accuracy)
    db.session.add(cs)
    db.session.commit()
    return jsonify({'ok': True, 'score_id': cs.id}), 201


def _competition_rankings_snapshot(comp_id, limit=50):
    # simple: get latest score per user ordered by wpm, accuracy
    rows = (
        CompetitionScore.query
        .filter_by(competition_id=comp_id)
        .order_by(CompetitionScore.wpm.desc(), CompetitionScore.accuracy.desc())
        .limit(limit)
        .all()
    )

    out = []
    for s in rows:
        user = User.query.get(s.user_id)
        out.append({
            'user_id': s.user_id,
            'username': user.username if user else f'User {s.user_id}',
            'wpm': s.wpm,
            'accuracy': s.accuracy
        })

    return out


@bp.route('/competitions/<int:comp_id>/rankings')
def api_competition_rankings(comp_id):
    data = _competition_rankings_snapshot(comp_id, limit=100)
    return jsonify(data)


@bp.route('/competitions/<int:comp_id>/live')
def competitions_live(comp_id):
    comp = Competition.query.get_or_404(comp_id)

    def gen():
        try:
            while True:
                snapshot = _competition_rankings_snapshot(comp_id, limit=50)
                payload = {'rankings': snapshot}
                yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(3)
        except GeneratorExit:
            return

    return Response(stream_with_context(gen()), mimetype='text/event-stream')


@bp.route('/competitions/<int:comp_id>/remove-user', methods=['POST'])
def remove_user_from_competition(comp_id):
    comp = Competition.query.get_or_404(comp_id)
    user_id = session.get('user_id')
    if not user_id or comp.manager_id != user_id:
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json() or {}
    csrf = data.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    remove_id = data.get('user_id')
    if not remove_id:
        return jsonify({'error': 'missing_user'}), 400

    part = CompetitionParticipant.query.filter_by(competition_id=comp.id, user_id=remove_id).first()
    if not part:
        return jsonify({'error': 'not_found'}), 404
    db.session.delete(part)
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/competitions/<int:comp_id>/delete', methods=['POST'])
def delete_competition(comp_id):
    comp = Competition.query.get_or_404(comp_id)
    user_id = session.get('user_id')
    if not user_id or comp.manager_id != user_id:
        return jsonify({'error': 'forbidden'}), 403

    csrf = request.form.get('csrf_token') or (request.get_json() or {}).get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    db.session.delete(comp)
    db.session.commit()
    return jsonify({'ok': True})



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