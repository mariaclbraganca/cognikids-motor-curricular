import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_pymongo import PyMongo

load_dotenv()

# Objetos globais para extensões Flask
mongo = PyMongo()
bcrypt = Bcrypt()

logger = logging.getLogger(__name__)

# (modulo, atributo do blueprint, prefixo de URL)
BLUEPRINTS = [
    ('auth_controller', 'auth_blueprint', '/api'),
    ('iot_controller', 'iot_bp', '/api/iot'),
    ('student_controller', 'student_blueprint', '/api/students'),
    ('teacher_controller', 'teacher_blueprint', '/api/teachers'),
    ('parent_controller', 'parent_blueprint', '/api/parents'),
    ('class_controller', 'class_blueprint', '/api/classes'),
    ('grade_controller', 'grade_blueprint', '/api/grades'),
    ('challenge_controller', 'challenge_blueprint', '/api/challenges'),
    ('message_controller', 'message_blueprint', '/api'),
    ('notification_controller', 'notification_blueprint', '/api'),
    ('schedule_controller', 'schedule_blueprint', '/api/schedule'),
    ('forum_controller', 'forum_blueprint', '/api'),
    ('gallery_controller', 'gallery_blueprint', '/api'),
    ('qa_controller', 'qa_blueprint', '/api'),
    ('support_kit_controller', 'support_kit_bp', '/api/support-kit'),
    ('consent_controller', 'consent_blueprint', '/api/consent'),
    ('accessibility_controller', 'accessibility_blueprint', '/api/accessibility'),
    ('break_controller', 'break_blueprint', '/api/breaks'),
]


def _configurar_logging(app):
    nivel = logging.DEBUG if app.config.get('DEBUG') else logging.INFO
    logging.basicConfig(
        level=nivel,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    )


def create_app(config_overrides=None):
    app = Flask(__name__)

    app.config['MONGO_URI'] = os.getenv('MONGO_URI')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

    # Timeouts e pool de conexoes do MongoDB
    app.config['MONGO_CONNECT_TIMEOUT_MS'] = 5000
    app.config['MONGO_SERVER_SELECTION_TIMEOUT_MS'] = 5000
    app.config['MONGO_SOCKET_TIMEOUT_MS'] = 10000
    app.config['MONGO_MAX_POOL_SIZE'] = 50
    app.config['MONGO_MIN_POOL_SIZE'] = 10

    # Limite de upload (galeria de criacoes dos alunos)
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_BYTES', 5 * 1024 * 1024))

    # URL do gateway do satelite — usada so pela cascata de revogacao de
    # consentimento (Utils/satellite_client.py, ADR-008/ADR-010). Opcional
    # por natureza: o core continua funcionando sem o satelite (CLAUDE.md
    # secao 2), entao a ausencia desta variavel nunca impede o core de subir.
    app.config['SATELLITE_BASE_URL'] = os.getenv('SATELLITE_BASE_URL', 'http://localhost:8001')

    if config_overrides:
        app.config.update(config_overrides)

    _configurar_logging(app)

    if not app.config.get('SECRET_KEY'):
        raise RuntimeError(
            'SECRET_KEY nao definida. Copie .env.example para .env e preencha '
            'as chaves antes de iniciar a API.'
        )

    # CORS restrito as origens do dashboard. '*' permitia que qualquer site
    # aberto no navegador do professor chamasse a API com o token dele.
    origens = [
        o.strip()
        for o in os.getenv('CORS_ORIGINS', 'http://localhost:8501').split(',')
        if o.strip()
    ]
    CORS(app, resources={r'/api/*': {'origins': origens}}, supports_credentials=True)

    mongo.init_app(app)
    bcrypt.init_app(app)

    _registrar_blueprints(app)
    _registrar_rotas_base(app)
    _registrar_handlers_de_erro(app)

    return app


def _registrar_blueprints(app):
    import importlib

    for modulo_nome, atributo, prefixo in BLUEPRINTS:
        modulo = importlib.import_module(f'app.Controllers.{modulo_nome}')
        blueprint = getattr(modulo, atributo)
        app.register_blueprint(blueprint, url_prefix=prefixo)
        logger.info('Blueprint registrado: %s -> %s', atributo, prefixo)


def _registrar_rotas_base(app):
    @app.route('/')
    def index():
        return jsonify({
            'status': 'sucesso',
            'message': 'Servidor CogniKids no ar!',
            'api': '/api',
            'status_endpoint': '/api/status',
        })

    def _status():
        """Health check: valida tambem a conectividade com o MongoDB."""
        try:
            mongo.db.command('ping')
            db_ok = True
        except Exception as e:
            logger.warning('Health check: MongoDB indisponivel: %s', e)
            db_ok = False

        payload = {
            'status': 'sucesso' if db_ok else 'degradado',
            'message': 'Servidor funcionando corretamente!' if db_ok
                       else 'API no ar, mas sem conexao com o banco de dados',
            'database': 'ok' if db_ok else 'indisponivel',
        }
        return jsonify(payload), 200 if db_ok else 503

    # /status e /api/status: a documentacao citava o segundo, que nao existia
    app.add_url_rule('/status', 'status', _status)
    app.add_url_rule('/api/status', 'api_status', _status)


def _registrar_handlers_de_erro(app):
    """Respostas JSON consistentes: a API nunca deve devolver HTML."""

    @app.errorhandler(400)
    def _400(e):
        return jsonify({'status': 'erro', 'message': 'Requisicao invalida'}), 400

    @app.errorhandler(404)
    def _404(e):
        return jsonify({'status': 'erro', 'message': 'Recurso nao encontrado'}), 404

    @app.errorhandler(405)
    def _405(e):
        return jsonify({'status': 'erro', 'message': 'Metodo nao permitido'}), 405

    @app.errorhandler(413)
    def _413(e):
        return jsonify({'status': 'erro', 'message': 'Arquivo excede o tamanho maximo'}), 413

    @app.errorhandler(500)
    def _500(e):
        logger.error('Erro nao tratado: %s', e)
        return jsonify({'status': 'erro', 'message': 'Erro interno do servidor'}), 500
