# Import necessary libraries for Flask web app, AWS S3 access, and database connection
from flask import Flask, request
from dotenv import load_dotenv
import os, json, requests
import boto3
from PIL import Image
import io
import logging
import urllib
import cv2
import uuid
import tensorflow as tf
import numpy as np
from tinydb import TinyDB, Query

# curl -X POST -F "img=@/Users/jakubsiekiera/Downloads/photo.png" -F "camera_id=123" https://secureeye.herokuapp.com/upload

# TODO try to reduce the size of the app
# TODO test the tinydb

# Create a logger object
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)  # Set log level to INFO. Change it to DEBUG, ERROR, WARN as per your requirement.

# Load environment variables from a .env file
def configure_secrets():
    load_dotenv()
    logger.info("Environment Variables Loaded")

configure_secrets()

# Create a Flask web application
app = Flask(__name__)

# Load AWS S3 Access keys from environment variables
S3_ACCESS_KEY = os.getenv('S3_ACCESS_KEY')
S3_SECRET_ACCESS_KEY = os.getenv('S3_SECRET_ACCESS_KEY')

# Set up AWS S3 client with the access keys
boto3.setup_default_session(aws_access_key_id=S3_ACCESS_KEY,
                            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
                            region_name='eu-west-1')
s3 = boto3.client('s3')
logger.info("AWS S3 client initialized")

# Download the database if it exists, if not, create a new one
try:
    s3.download_file('images-for-messenger', 'db.json', 'db.json')
    logger.info("Downloaded the database from S3.")
except Exception as e:
    logger.info("Database does not exist, a new one will be created.")

db = TinyDB('db.json')
logger.info("Database initialized")

# TODO user's PSID might change in the future so internally should be
# referenced by the UserId incremental

# Create tables if they don't exist. TinyDB automatically creates a new table if it doesn't exist
user_psid = db.table('user_psid')  # Table for user_psid
user_camera = db.table('user_camera')  # Table for user_camera
logger.info("Database tables created")

# # Upload the database to S3 if it's a new one
# if not os.path.isfile('db.json'):
#     s3.upload_file('db.json', 'images-for-messenger', 'db.json')
#     logger.info("Uploaded the new database to S3.")

UserQuery = Query()

MODEL_PATH = os.getenv('MODEL_PATH')

s3.download_file('images-for-messenger', MODEL_PATH, MODEL_PATH)

# TODO model will be discarded after 7 days so the need is for a new s3 bucket specifically for models
# Download the model file to the local (Heroku Dyno) file system

# Load TFLite model and allocate tensors.
interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
interpreter.allocate_tensors()

# Get input and output tensors.
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()


# Define a route for the home page
@app.route('/')
def home():
    return "Say 'Hi!' to SecureEye!"


# Send response message to a Facebook Messenger user
def sendResponseToMessenger(sender_psid, response):
    PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN')

    # Define the payload for the POST request
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
    logger.info(f"Response sent to messenger. Response text: {r.text}")


# Route for uploading image to AWS S3
@app.route('/upload', methods=['POST'])
def uploadImageToS3():
    # Retrieve the file from the request
    image_raw_bytes = request.files['img']

    # Retrieve the camera_id from the request
    camera_id = request.form.get('camera_id')

    # Convert raw bytes into Image object
    image = Image.open(io.BytesIO(image_raw_bytes.read()))

    # Resize the image to the size your model expects
    image_for_model = image.resize((224, 224))

    # Convert image to numpy array and normalize it
    image_for_model = np.array(image_for_model) / 255.0

    image_for_model = np.expand_dims(image_for_model, axis=0).astype(np.float32)

    # Set tensor to image
    interpreter.set_tensor(input_details[0]['index'], image_for_model)

    # Run inference
    interpreter.invoke()

    # Get output tensor
    output_data = interpreter.get_tensor(output_details[0]['index'])

    # Normalize prediction
    prediction = np.zeros_like(output_data[0])
    prediction[np.argmax(output_data[0])] = 1

    # Create a bytes buffer
    image_byte_arr = io.BytesIO()

    # Save the image to the bytes buffer in PNG format
    image.save(image_byte_arr, format='PNG')

    # Get the byte value of the buffer
    image_byte_value = image_byte_arr.getvalue()

    # Define S3 resource instead of client to use the upload_file method
    s3 = boto3.resource('s3')
    key = str(uuid.uuid4()) + ".png"

    # Put image into S3 bucket
    s3.Bucket('images-for-messenger').put_object(Key=key, Body=image_byte_value)
    logger.info("Image uploaded to S3")

    # If the human is in the image, send the image URL to the Facebook Messenger user
    if prediction[1] == 1:
        logger.info("Human detected in the image")
        # Create a URL for the uploaded file
        image_url = f"https://images-for-messenger.s3.eu-west-1.amazonaws.com/{key}"

        # Send the URL to the image on S3 bucket to Facebook Messenger User asscoiated with the CameraId
        response = {
            'attachment': {
                'type': 'file',
                'payload': {
                    'url': image_url,
                    'is_reusable': True
                }
            }
        }

        # TODO update user's PSID if it has changed
        # Find the user associated with this CameraId
        # Search for user_camera with given CameraId
        camera = user_camera.search(UserQuery.CameraId == camera_id)

        # Search for user_psid with the PSID of the first found user_camera
        if camera:
            user = user_psid.search(UserQuery.PSID == camera[0]['PSID'])
            logger.info("Found the user associated with the CameraId")
            if user:
                # Send the image URL to the Facebook Messenger user
                sendResponseToMessenger(user[0]['PSID'], response)
                logger.info("Sent image URL to Facebook Messenger user")
    else:
        logger.info("Human not detected in the image")

    return 'File uploaded successfully', 200


# Handle incoming messages from Facebook Messenger
def handleMessage(sender_psid, received_message):
    # Process the received message and send a response
    if 'attachments' in received_message:
        for attachment in received_message['attachments']:
            if attachment['type'] == 'image':
                # Get the image URL
                image_url = attachment['payload']['url']

                # Use urllib to download the image
                image_on_disk, _ = urllib.request.urlretrieve(image_url)

                # Convert image into .png format
                image = Image.open(image_on_disk)
                image.save("temp.png")

                # Decode the QR code from the image
                img = cv2.imread('temp.png', cv2.IMREAD_GRAYSCALE)
                _, img2 = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)

                qrCodeDetector = cv2.QRCodeDetector()
                decodedText, _, _ = qrCodeDetector.detectAndDecode(img2)

                # If QR code is decoded successfully, get the CameraId
                if decodedText:
                    logger.info(f"QR code is decoded successfully")
                    # TODO allow the user for being able to perform multiple reregistrations if the first one was accidental
                    camera_id = decodedText
                    logger.info("Decoded the QR code.")

                    # Check if the user already exists
                    user = user_psid.search(UserQuery.PSID == sender_psid)
                    if not user:
                        # Create a new user if it does not exist
                        user_psid.insert({'PSID': sender_psid})
                        logger.info("New user created.")

                    # Assign the cameraID to the user
                    user_camera.insert({'CameraId': camera_id, 'PSID': sender_psid})
                    logger.info("Saved the user and camera id to the database.")

                    s3.upload_file('db.json', 'images-for-messenger', 'db.json')
                    logger.info("Uploaded the database to S3.")
    
                    response = {
                        'text': f"Successfully registered your camera!"
                    }
                else:
                    logger.info(f"Could not decode QR code")
                    response = {
                        'text': f"Could not decode QR code. Please try again."
                    }

                os.remove("temp.png")  # Remove the local temporary file
                sendResponseToMessenger(sender_psid, response)


VERIFY_TOKEN = os.getenv('VERIFY_TOKEN') # Replace this with your verify token


# Define a webhook route for Facebook Messenger
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # Verify the webhook for Facebook Messenger
    if request.method == 'GET':

        logger.info('Verifying the webhook...')

        if 'hub.mode' in request.args:
            mode = request.args.get('hub.mode')
        if 'hub.verify_token' in request.args:
            token = request.args.get('hub.verify_token')
        if 'hub.challenge' in request.args:
            challenge = request.args.get('hub.challenge')

        logger.info('Got mode, token and challenge...')

        if 'hub.mode' in request.args and 'hub.verify_token' in request.args:
            mode = request.args.get('hub.mode')
            token = request.args.get('hub.verify_token')

            if mode == 'subscribe' and token == VERIFY_TOKEN:
                
                logger.info('WEBHOOK_VERIFIED')

                challenge = request.args.get('hub.challenge')

                return challenge, 200
            else:
                return 'ERROR', 403
            
        return 'SOMETHING', 200

    # Handle incoming POST requests from Facebook Messenger
    if request.method == 'POST':

        logger.info('Received the message from the messenger user.')

        if 'hub.mode' in request.args:
            mode = request.args.get('hub.mode')
        if 'hub.verify_token' in request.args:
            token = request.args.get('hub.verify_token')
        if 'hub.challenge' in request.args:
            challenge = request.args.get('hub.challenge')

        if 'hub.mode' in request.args and 'hub.verify_token' in request.args:
            mode = request.args.get('hub.mode')
            token = request.args.get('hub.verify_token')

            if mode == 'subscribe' and token == VERIFY_TOKEN:  
                logger.info('WEBHOOK_VERIFIED')

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

                sender_psid = webhook_event['sender']['id']
                logger.info(f"Sender PSID: {sender_psid}")
                if 'message' in webhook_event:
                    handleMessage(sender_psid, webhook_event['message'])
                    logger.info("Handled incoming message")

                return 'EVENT_RECEIVED', 200
        else:
            return 'ERROR', 404


# Run the Flask web application
if __name__ == "__main__":
    logger.info("Running Flask application")
    app.run()
