import os

from app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))

    # Debug NUNCA deve vir ligado por padrao: o console interativo do
    # Werkzeug permite execucao remota de codigo. Ative explicitamente com
    # FLASK_DEBUG=1 apenas em desenvolvimento.
    debug = os.environ.get('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes')

    app.run(host='0.0.0.0', port=port, debug=debug)
