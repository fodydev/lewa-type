from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'

    def set_password(self, raw_password: str):
        self.password = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password, raw_password)

    # relationship to scores
    scores = db.relationship('Score', backref='user', lazy=True)


class Competition(db.Model):
    __tablename__ = 'competition'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(16), nullable=False, index=True)
    is_public = db.Column(db.Boolean, default=True, nullable=False)
    allow_join = db.Column(db.Boolean, default=True, nullable=False)
    live_ranking = db.Column(db.Boolean, default=True, nullable=False)
    manager_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    manager = db.relationship('User', backref=db.backref('managed_competitions', lazy='dynamic'))
    participants = db.relationship('CompetitionParticipant', backref='competition', cascade='all, delete-orphan', lazy=True)
    invites = db.relationship('CompetitionInvite', backref='competition', cascade='all, delete-orphan', lazy=True)
    scores = db.relationship('CompetitionScore', backref='competition', cascade='all, delete-orphan', lazy=True)

    def __repr__(self):
        return f'<Competition {self.title} lang={self.language} public={self.is_public}>'


class CompetitionParticipant(db.Model):
    __tablename__ = 'competition_participant'
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competition.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('competitions', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('competition_id', 'user_id', name='uq_competition_user'),
    )


class CompetitionInvite(db.Model):
    __tablename__ = 'competition_invite'
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competition.id'), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), nullable=True)
    invited_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    used = db.Column(db.Boolean, default=False, nullable=False)

    inviter = db.relationship('User', backref=db.backref('sent_invites', lazy='dynamic'))

    def is_valid(self):
        if self.used:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True


class CompetitionScore(db.Model):
    __tablename__ = 'competition_score'
    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competition.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    wpm = db.Column(db.Integer, nullable=False)
    accuracy = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('competition_scores', lazy='dynamic'))

    __table_args__ = (
        db.Index('ix_competition_user_created', 'competition_id', 'user_id', 'created_at'),
    )


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    language = db.Column(db.String(16), nullable=False)
    wpm = db.Column(db.Integer, nullable=False)
    accuracy = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Score user_id={self.user_id} wpm={self.wpm} acc={self.accuracy}%>'
