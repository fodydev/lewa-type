# routes.py
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, make_response, Response, stream_with_context, jsonify, json
from app import db
from app.models import User, Score, Competition, CompetitionParticipant, CompetitionInvite, CompetitionScore
from flask_jwt_extended import create_access_token, unset_jwt_cookies, set_access_cookies
from flask_login import login_user, logout_user, login_required, current_user
import secrets
import time
from datetime import datetime
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
    return render_template('home.html', languages=languages, selected_lang=lang, title='Home', csrf_token=csrf, is_authenticated=current_user.is_authenticated)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        flash('You are already logged in.', 'info')
        return redirect(url_for('routes.home'))

    if request.method == 'GET':
        return render_template('login.html', csrf_token=_generate_csrf_token())

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

    # Success: use flask_login
    login_user(user, remember=True)
    access_token = create_access_token(identity=str(user.id))
    resp = make_response(redirect(url_for('routes.home')))
    set_access_cookies(resp, access_token)
    flash('Logged in successfully!', 'success')
    return resp


@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        flash('You are already logged in.', 'info')
        return redirect(url_for('routes.home'))

    if request.method == 'GET':
        return render_template('signup.html', csrf_token=_generate_csrf_token())

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

    if User.query.filter((User.username == username) | (User.email == email)).first():
        flash('Username or email already exists', 'warning')
        return redirect(url_for('routes.signup'))

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user, remember=True)
    access_token = create_access_token(identity=str(user.id))
    resp = make_response(redirect(url_for('routes.home')))
    set_access_cookies(resp, access_token)
    flash('Account created and logged in!', 'success')
    return resp


@bp.route('/logout', methods=['POST'])
def logout():
    csrf = request.form.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        flash('Invalid CSRF token', 'danger')
        return redirect(url_for('routes.home'))

    logout_user()
    resp = make_response(redirect(url_for('routes.home')))
    unset_jwt_cookies(resp)
    flash('Logged out successfully', 'info')
    return resp


@bp.route('/save-score', methods=['POST'])
@login_required
def save_score():
    data = request.get_json() or {}
    csrf = data.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    language_code = data.get('language')
    language = languages.get(language_code, language_code)
    wpm = data.get('wpm')
    accuracy = data.get('accuracy')

    try:
        wpm = int(wpm)
        accuracy = float(accuracy)
    except Exception:
        return jsonify({'error': 'invalid_data'}), 400

    score = Score(user_id=current_user.id, language=language, wpm=wpm, accuracy=accuracy)
    db.session.add(score)
    db.session.commit()

    return jsonify({'ok': True, 'score_id': score.id, 'created_at': score.created_at.isoformat()}), 201


@bp.route('/competitions')
@login_required
def competitions_page():
    csrf = _generate_csrf_token()
    return render_template('competitions.html', languages=languages, csrf_token=csrf)


@bp.route('/api/competitions')
@login_required
def api_competitions():
    user_id = current_user.id
    q = Competition.query.filter(
        (Competition.is_public == True) |
        (Competition.manager_id == user_id) |
        Competition.id.in_(
            db.session.query(CompetitionParticipant.competition_id)
            .filter(CompetitionParticipant.user_id == user_id)
        )
    ).order_by(Competition.created_at.desc())

    comps = q.all()
    out = []
    for c in comps:
        out.append({
            'id': c.id,
            'title': c.title,
            'language': c.language,
            'is_public': c.is_public,
            'is_manager': c.manager_id == user_id
        })
    return jsonify(out)


@bp.route('/competitions/new')
@login_required
def create_competition_page():
    return render_template('competition_create.html', languages=languages, csrf_token=_generate_csrf_token())


@bp.route('/competitions', methods=['POST'])
@login_required
def create_competition():
    data = request.get_json() or {}
    csrf = data.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    title = (data.get('title') or '').strip()
    lang_code = data.get('language')
    is_public = bool(data.get('is_public'))
    live_ranking = bool(data.get('live_ranking'))

    if not title or not lang_code:
        return jsonify({'error': 'missing_fields'}), 400

    comp = Competition(
        title=title,
        language=lang_code,
        is_public=is_public,
        live_ranking=live_ranking,
        manager_id=current_user.id
    )
    db.session.add(comp)
    db.session.flush()  # Get comp.id

    # Auto-join creator
    part = CompetitionParticipant(competition_id=comp.id, user_id=current_user.id)
    db.session.add(part)
    db.session.commit()

    return jsonify({'ok': True, 'competition_id': comp.id}), 201


@bp.route('/competitions/<int:comp_id>/manage')
@login_required
def manage_competition_page(comp_id):
    comp = Competition.query.get_or_404(comp_id)
    if comp.manager_id != current_user.id:
        flash('You do not have permission to manage this competition', 'danger')
        return redirect(url_for('routes.competitions_page'))
    return render_template('competition_manage.html', comp_id=comp.id, csrf_token=_generate_csrf_token())


@bp.route('/competitions/<int:comp_id>/play')
@login_required
def play_competition(comp_id):
    comp = Competition.query.get_or_404(comp_id)

    # Auto-join public competitions
    if comp.is_public:
        participant = CompetitionParticipant.query.filter_by(
            competition_id=comp.id, user_id=current_user.id
        ).first()
        if not participant:
            participant = CompetitionParticipant(competition_id=comp.id, user_id=current_user.id)
            db.session.add(participant)
            db.session.commit()
    else:
        # Private: must be invited or manager
        if comp.manager_id != current_user.id:
            participant = CompetitionParticipant.query.filter_by(
                competition_id=comp.id, user_id=current_user.id
            ).first()
            if not participant:
                flash('You do not have access to this private competition.', 'danger')
                return redirect(url_for('routes.competitions_page'))

    return render_template(
        'competition_play.html',
        comp_id=comp.id,
        title=comp.title,
        language=comp.language,
        csrf_token=_generate_csrf_token(),
        is_authenticated=True
    )


@bp.route('/api/competitions/<int:comp_id>/participants')
@login_required
def api_competition_participants(comp_id):
    Competition.query.get_or_404(comp_id)  # Just to 404 if not exist
    parts = (
        db.session.query(CompetitionParticipant, User.username)
        .join(User, User.id == CompetitionParticipant.user_id)
        .filter(CompetitionParticipant.competition_id == comp_id)
        .order_by(CompetitionParticipant.joined_at.asc())
        .all()
    )
    out = [{'id': p.user_id, 'username': username} for p, username in parts]
    return jsonify(out)


@bp.route('/competitions/<int:comp_id>/invite', methods=['POST'])
@login_required
def create_invite(comp_id):
    comp = Competition.query.get_or_404(comp_id)
    if comp.manager_id != current_user.id:
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json() or {}
    csrf = data.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    token = secrets.token_urlsafe(8)
    invite = CompetitionInvite(competition_id=comp.id, token=token, invited_by=current_user.id)
    db.session.add(invite)
    db.session.commit()
    return jsonify({'ok': True, 'invite_token': token})


@bp.route('/competitions/join', methods=['POST'])
@login_required
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

    exists = CompetitionParticipant.query.filter_by(
        competition_id=invite.competition_id, user_id=current_user.id
    ).first()
    if exists:
        return jsonify({'ok': True, 'message': 'already_joined'})

    part = CompetitionParticipant(competition_id=invite.competition_id, user_id=current_user.id)
    invite.used = True
    db.session.add(part)
    db.session.commit()
    return jsonify({'ok': True, 'competition_id': invite.competition_id})


@bp.route('/competitions/<int:comp_id>/submit-score', methods=['POST'])
@login_required
def submit_competition_score(comp_id):
    data = request.get_json() or {}
    csrf = data.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    comp = Competition.query.get_or_404(comp_id)

    # Auto-join public competitions
    if comp.is_public:
        participant = CompetitionParticipant.query.filter_by(
            competition_id=comp.id, user_id=current_user.id
        ).first()
        if not participant:
            participant = CompetitionParticipant(competition_id=comp.id, user_id=current_user.id)
            db.session.add(participant)
            db.session.commit()
    else:
        if comp.manager_id != current_user.id:
            if not CompetitionParticipant.query.filter_by(
                competition_id=comp.id, user_id=current_user.id
            ).first():
                return jsonify({'error': 'not_participant'}), 403

    try:
        wpm = int(data.get('wpm'))
        accuracy = float(data.get('accuracy'))
        if wpm < 0 or accuracy < 0 or accuracy > 100:
            raise ValueError
    except Exception:
        return jsonify({'error': 'invalid_data'}), 400

    cs = CompetitionScore(competition_id=comp.id, user_id=current_user.id, wpm=wpm, accuracy=accuracy)
    db.session.add(cs)
    db.session.commit()
    return jsonify({'ok': True, 'score_id': cs.id}), 201


def _competition_rankings_snapshot(comp_id, limit=50):
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
@login_required
def api_competition_rankings(comp_id):
    Competition.query.get_or_404(comp_id)
    data = _competition_rankings_snapshot(comp_id, limit=100)
    return jsonify(data)


@bp.route('/competitions/<int:comp_id>/live')
@login_required
def competitions_live(comp_id):
    Competition.query.get_or_404(comp_id)

    def gen():
        try:
            while True:
                snapshot = _competition_rankings_snapshot(comp_id, limit=50)
                yield f"data: {json.dumps({'rankings': snapshot})}\n\n"
                time.sleep(3)
        except GeneratorExit:
            pass

    return Response(stream_with_context(gen()), mimetype='text/event-stream')


@bp.route('/competitions/<int:comp_id>/remove-user', methods=['POST'])
@login_required
def remove_user_from_competition(comp_id):
    comp = Competition.query.get_or_404(comp_id)
    if comp.manager_id != current_user.id:
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json() or {}
    csrf = data.get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    remove_id = data.get('user_id')
    if not remove_id:
        return jsonify({'error': 'missing_user'}), 400

    part = CompetitionParticipant.query.filter_by(competition_id=comp.id, user_id=remove_id).first()
    if part:
        db.session.delete(part)
        db.session.commit()
    return jsonify({'ok': True})


@bp.route('/competitions/<int:comp_id>/delete', methods=['POST'])
@login_required
def delete_competition(comp_id):
    comp = Competition.query.get_or_404(comp_id)
    if comp.manager_id != current_user.id:
        return jsonify({'error': 'forbidden'}), 403

    csrf = (request.get_json() or {}).get('csrf_token')
    if not csrf or csrf != session.get('csrf_token'):
        return jsonify({'error': 'invalid_csrf'}), 400

    db.session.delete(comp)
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/rankings')
def rankings():
    lang_code = request.args.get('lang') or session.get('lang') or 'gez'
    lang_name = languages.get(lang_code, lang_code)

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
        data.append({
            'username': username or f'User {score.user_id}',
            'language': score.language,
            'wpm': score.wpm,
            'accuracy': score.accuracy,
            'created_at': score.created_at.isoformat()
        })
    return jsonify(data)