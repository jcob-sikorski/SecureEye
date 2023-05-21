from flask import Flask, request
from dotenv import load_dotenv
import os, json, requests
import boto3
from werkzeug.utils import secure_filename

# TODO add new route for /upload to aws s3 bucket
# camera sends image to /upload which sends image to s3 bucket
# and flask app sends image url to facebook messenger

def configure_secrets():
    load_dotenv()


configure_secrets()

app = Flask(__name__)

S3_ACCESS_KEY = os.getenv('S3_ACCESS_KEY')
S3_SECRET_ACCESS_KEY = os.getenv('S3_SECRET_ACCESS_KEY')


boto3.setup_default_session(aws_access_key_id=S3_ACCESS_KEY,
                            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
                            region_name='eu-west-1')


s3 = boto3.client('s3')


@app.route('/')
def home():
    return "Say 'Hi!' to SecureEye!"


def sendResponseToMessenger(sender_psid, response):
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


def handleMessageFromUser(sender_psid, received_message):
    if 'text' in received_message:
        image_url = "https://www.usaoncanvas.com/images/low_res_image.jpg"

        response = {
            'attachment': {
                'type': 'image',
                'payload': {
                    'url': image_url,
                    'is_reusable': True
                }
            }
        }

        sendResponseToMessenger(sender_psid, response)
    else:
        response = {
            'text': f"This app only accepts text messages."
        }

        sendResponseToMessenger(sender_psid, response)

# TODO make it secure so only camera can upload to s3 bucket
# e.g. add a secret key to the request
@app.route('/upload', methods=['POST'])
def uploadImageToS3():
    if 'file' not in request.files:
        return 'No file part', 400

    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400

    if file:
        filename = secure_filename(file.filename)
        s3.upload_fileobj(file, 'images-for-messenger', filename)
        return 'File uploaded successfully', 200


# TODO do we actually upload this to heroku?
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN') # Replace this with your verify token


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
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
                    handleMessageFromUser(sender_psid, webhook_event['message'])

                return 'EVENT_RECEIVED', 200
        else:
            return 'ERROR', 404


if __name__ == '__main__':
    app.run()