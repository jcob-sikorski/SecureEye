from flask import Flask, request, abort
from dotenv import load_dotenv
import os, json, requests

app = Flask(__name__)


def callSendAPI(sender_psid, response):
    # TODO add access token to .env
    PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN')

    payload = {
        'recipient': {
            'id': sender_psid
        },
        'message': response,
        'messaging_type': 'RESPONSE'
    }


    headers = {
        'content-type': 'application/json'
    }

    url = f'https://graph.facebook.com/v16.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
    r = requests.post(url, json=payload, headers=headers)
    print(r.text)

def handleMessage(sender_psid, received_message):
    # TODO send image instead of text
    if 'text' in received_message:
        response = {
            'text': f"You sent the message: {received_message['text']}"
        }

        callSendAPI(sender_psid, response)
    else:
        response = {
            'text': f"This app only accepts text messages."
        }

        callSendAPI(sender_psid, response)


@app.route('/')
def home():
    return 'Flask heroku app.'


def configure():
    load_dotenv()


# TODO do we actually upload this to heroku?
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN') # Replace this with your verify token


@app.route('/webhook', methods=['GET', 'POST'])
def index():
    global VERIFY_TOKEN

    if request.method == 'GET':

        if 'hub.mode' in request.args:
            mode = request.args.get('hub.mode')
            print(mode)
        if 'hub.verify_token' in request.args:
            token = request.args.get('hub.verify_token')
            print(token)
        if 'hub.challenge' in request.args:
            challenge = request.args.get('hub.challenge')
            print(challenge)

        if 'hub.mode' in request.args and 'hub.verify_token' in request.args:
            mode = request.args.get('hub.mode')
            token = request.args.get('hub.verify_token')

            if mode == 'subscribe' and token == VERIFY_TOKEN:
                print('WEBHOOK_VERIFIED')

                challenge = request.args.get('hub.challenge')

                return challenge, 200
            else:
                return 'ERROR', 403
            
        return 'SOMETHING', 200


    if request.method == 'POST':

        if 'hub.mode' in request.args:
            mode = request.args.get('hub.mode')
            print(mode)
        if 'hub.verify_token' in request.args:
            token = request.args.get('hub.verify_token')
            print(token)
        if 'hub.challenge' in request.args:
            challenge = request.args.get('hub.challenge')
            print(challenge)

        if 'hub.mode' in request.args and 'hub.verify_token' in request.args:
            mode = request.args.get('hub.mode')
            token = request.args.get('hub.verify_token')

            if mode == 'subscribe' and token == VERIFY_TOKEN:  
                print('WEBHOOK_VERIFIED')

                challenge = request.args.get('hub.challenge')

                return challenge, 200
            else:
                return 'ERROR', 403
            



        data = request.data
        body = json.loads(data.decode('utf-8'))

        if 'object' in body and body['object'] == 'page':
            entries = body['entry']

            for entry in entries:
                webhook_event = entry['messaging'][0]
                print(webhook_event)

                sender_psid = webhook_event['sender']['id']
                print(f'Sender PSID: {sender_psid}')

                if 'message' in webhook_event:
                    handleMessage(sender_psid, webhook_event['message'])

                return 'EVENT_RECEIVED', 200
        else:
            return 'ERROR', 404

if __name__ == '__main__':
    configure()
    app.run()