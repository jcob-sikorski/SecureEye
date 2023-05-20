# from flask import Flask

# app = Flask(__name__)

# @app.route('/')
# def home():
#     return 'Flask heroku app.'

# if __name__ == '__main__':
#     app.run()

from flask import Flask, request, abort
from dotenv import load_dotenv
import os

def configure():
    load_dotenv()

app = Flask(__name__)

VERIFY_TOKEN = os.getenv('VERIFY_TOKEN') # Replace this with your verify token

@app.route('/messaging-webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode and token:
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge
        else:
            abort(403)  # Forbidden

if __name__ == "__main__":
    configure()
    app.run(port=5000, debug=True)
