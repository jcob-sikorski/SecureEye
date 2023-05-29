# Import necessary libraries for Flask web app, AWS S3 access, and database connection
from flask import Flask, request
from dotenv import load_dotenv
import os, json, requests
import boto3
from PIL import Image
import io
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect

# curl -X POST --data-binary "@/Users/jakubsiekiera/Downloads/25percent4x4.png" https://secureeye.herokuapp.com/upload
# curl -X POST -F "file=@/Users/jakubsiekiera/Downloads/25percent4x4.png" https://secureeye.herokuapp.com/upload

# Load environment variables from a .env file
def configure_secrets():
    load_dotenv()

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

# Load database details from environment variables
db_name = os.getenv('DB_NAME')
db_user = os.getenv('DB_USER')
db_psswd = os.getenv('DB_PSSWD')

# Configure SQLAlchemy to use PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{db_user}:{db_psswd}@ec2-3-83-61-239.compute-1.amazonaws.com/{db_name}'
db = SQLAlchemy(app)


# Define database models for SQLAlchemy
class UserPSID(db.Model):
    __tablename__ = 'user_psid'
    UserId = db.Column(db.Integer, primary_key=True)

class UserCamera(db.Model):
    __tablename__ = 'user_camera'
    CameraId = db.Column(db.Integer, primary_key=True)
    UserId = db.Column(db.Integer, db.ForeignKey('user_psid.UserId'))  # Foreign Key reference to the UserPSID table


with app.app_context():
    inspector = inspect(db.engine)
    if 'user_psid' not in inspector.get_table_names():
        db.create_all()


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
        'Content-Type': 'application/json'
    }

    url = f'https://graph.facebook.com/v16.0/me/messages?access_token={PAGE_ACCESS_TOKEN}'
    r = requests.post(url, json=payload, headers=headers)
    print(r.text)


# TODO reading and saving to the db doen't work, 
# hence the problems with sending the response to the user

# Route for uploading image to AWS S3
@app.route('/upload', methods=['POST'])
def uploadImageToS3():
    # TODO send the curl request with the camera id included with image data

    # Retrieve and process image data from the request
    image_raw_bytes = request.get_data() 

    # Convert raw bytes into Image object
    image = Image.open(io.BytesIO(image_raw_bytes))

    # Convert image into .png format
    image.save("temp.png")

    # Open the saved image file in read bytes mode
    file = open("temp.png", "rb")

    # Define S3 resource instead of client to use the upload_file method
    s3 = boto3.resource('s3')
    s3.Bucket('images-for-messenger').put_object(Key="temp.png", Body=file)

    # Create a URL for the uploaded file
    image_url = f"https://images-for-messenger.s3.eu-west-1.amazonaws.com/temp.png"
    print(image_url)

    # Send the URL to the image on S3 bucket to Facebook Messenger User asscoiated with the CameraId
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

    # Store image URL in the database
    camera_id = 123  # replace with actual CameraId

    # TODO after getting the registration message from the user, save the PSID in the database
    # TODO can't find the user so can't send the response
    # Find the user associated with this CameraId
    user_camera = UserCamera.query.filter_by(CameraId=camera_id).first()
    if user_camera:
        user = UserPSID.query.filter_by(UserId=user_camera.UserId).first()
        if user:
            # Send the image URL to the Facebook Messenger user
            sendResponseToMessenger(user.PSID, response)
            
    file.close()  # Ensure to close the file after upload
    os.remove("temp.png")  # Remove the local temporary file

    return 'File uploaded successfully', 200


# Handle incoming messages from Facebook Messenger
def handleMessage(sender_psid, received_message):
    # Process the received message and send a response
    if 'text' in received_message:
        sender_psid = int(sender_psid)
        # TODO test saving the user PSID in the database
        # Check if the user already exists
        user = UserPSID.query.filter_by(PSID=sender_psid).first()
        if not user:
            # Create a new user if it does not exist
            user = UserPSID(UserId=sender_psid)
            db.session.add(user)
            db.session.flush()  # Make sure the user is added before the camera

        # Assuming the text message contains the CameraId
        camera_id = int(received_message['text'])

        # TODO test saving the camera ID in the database
        # Assign the cameraID to the user
        user_camera = UserCamera(CameraId=camera_id, UserId=sender_psid)
        db.session.add(user_camera)
        db.session.commit()

        response = {
            'text': f"Successfully registered your camera!"
        }
        sendResponseToMessenger(sender_psid, response)



VERIFY_TOKEN = os.getenv('VERIFY_TOKEN') # Replace this with your verify token


# Define a webhook route for Facebook Messenger
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # Verify the webhook for Facebook Messenger
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

    # Handle incoming POST requests from Facebook Messenger
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


# Run the Flask web application
if __name__ == "__main__":
    app.run()