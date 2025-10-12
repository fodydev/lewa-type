from flask import Blueprint, render_template, request, session

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
    return render_template('home.html', languages=languages, selected_lang=lang ,title='Home')