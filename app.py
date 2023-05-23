from flask import Flask, request
from dotenv import load_dotenv
import os, json, requests
import boto3
from werkzeug.utils import secure_filename

# TODO establish connection with messenger by webhook but retrieve messages when someone sends image to /upload and then send them to messenger user specified by pasted URL

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
        'Content-Type': 'application/json'
    }

    url = f'https://graph.facebook.com/v16.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
    r = requests.post(url, json=payload, headers=headers)
    print(r.text)


UPLOAD_SECRET_KEY = os.getenv('UPLOAD_SECRET_KEY')


@app.route('/upload', methods=['POST'])
def uploadImageToS3():
    # Check if the secret key is correct
    provided_secret_key = request.headers.get('UPLOAD-SECRET-KEY')

    if provided_secret_key != UPLOAD_SECRET_KEY:
        return 'Invalid secret key', 403
    
    if 'file' not in request.files:
        return 'No file part', 400

    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400

    if file:
        filename = secure_filename(file.filename)
        s3.upload_fileobj(file, 'images-for-messenger', filename)

        # Create a presigned URL for the uploaded file
        image_url = s3.generate_presigned_url('get_object',
                                                  Params={'Bucket': 'images-for-messenger',
                                                          'Key': filename},
                                                  ExpiresIn=3600)

        # Send the presigned URL to the image on S3 bucket to Facebook Messenger User
        response = {
            'attachment': {
                'type': 'image',
                'payload': {
                    'url': image_url,
                    'is_reusable': True
                }
            }
        }

        sender_psid = "5930112510450871"
        sendResponseToMessenger(sender_psid, response)

        return 'File uploaded successfully', 200


VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')

if __name__ == "__main__":
    app.run()
