# Import necessary libraries for Flask web app, AWS S3 access, and database connection
from flask import Flask, request
from dotenv import load_dotenv
import os
import boto3
from PIL import Image
import io
import logging
from io import BytesIO
import cv2
import uuid
import tensorflow as tf
import numpy as np
from tinydb import TinyDB, Query
import telebot


# TODO change messenger for telegram everywhere
# TODO change the name of s3 bucket

# curl -X POST -F "img=@/Users/jakubsiekiera/Downloads/photo.png" -F "camera_id=12345" https://clownfish-app-wrk3z.ondigitalocean.app/upload

# Create a logger object
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)  # Set log level to INFO. Change it to DEBUG, ERROR, WARN as per your requirement.


# Load environment variables from a .env file
def configure_secrets():
    load_dotenv()
    logger.info("Environment Variables Loaded")

configure_secrets()


BOT_FATHER_TOKEN = os.getenv('BOT_FATHER_TOKEN')
bot = telebot.TeleBot(BOT_FATHER_TOKEN)

bot.remove_webhook()
bot.set_webhook(url='https://clownfish-app-wrk3z.ondigitalocean.app/' + BOT_FATHER_TOKEN)

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


# Create tables if they don't exist. TinyDB automatically creates a new table if it doesn't exist
chat_ids = db.table('chat_ids')  # Table for user_psid
chat_ids_camera = db.table('chat_ids_camera')  # Table for user_camera
logger.info("Database tables created")

UserQuery = Query()

MODEL_PATH = os.getenv('MODEL_PATH')

s3.download_file('images-for-messenger', MODEL_PATH, MODEL_PATH)

# TODO model will be discarded after 7 days so the need is for a new s3 bucket specifically for models

# Load TFLite model and allocate tensors.
interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
interpreter.allocate_tensors()

logger.info("Model loaded")

# Get input and output tensors.
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

logger.info("Got input and output details")


# Route for uploading image to AWS S3
@app.route('/upload', methods=['POST'])
def uploadImageToS3():
    logger.info(f"Request the request from the camera: {request}")
    # Log the headers
    logger.info(f"Request headers: {request.headers}")
    # Log the request data (content)
    logger.info(f"Request data: {request.get_data()}")
	
    packet_size = request.headers.get('Content-Length')
    logger.info(f"Packet size: {packet_size}")
	
    # Retrieve the file from the request
    image_raw_bytes = request.files['img']

    # Retrieve the camera_id from the request
    camera_id = request.headers.get('camera_id')

    # Convert raw bytes into Image object
    image = Image.open(io.BytesIO(image_raw_bytes.read()))

    # Convert grayscale or RGBA images to RGB
    if image.mode != 'RGB':
        image = image.convert('RGB')

    # Resize the image to the size your model expects
    image_for_model = image.resize((224, 224))

    # Convert image to numpy array and normalize it
    image_for_model = np.array(image_for_model) / 255.0

    # The image processing and prediction seems correct if your model expects a (1, 224, 224, 3) input shape. 
    # Now, this code will also handle if the image doesn't have 3 channels.

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
    key = f"{uuid.uuid4()}.png"

    # Put image into S3 bucket
    s3.Bucket('images-for-messenger').put_object(Key=key, Body=image_byte_value)
    logger.info("Image uploaded to S3")

    # If the human is in the image, send the image URL to the Facebook Messenger user
    if prediction[1] == 1:
        logger.info("Human detected in the image")

        # TODO update chatID if it has changed

        #Find the user associated with this CameraId
        #Search for user_camera with given CameraId
        user_camera = chat_ids_camera.search(UserQuery.CameraId == camera_id)

        #Search for user_psid with the PSID of the first found user_camera
        if user_camera:
            logger.info("Found the user associated with the CameraId")
            user = user_camera[0]["ChatId"] # there is one user for the camera so we take the first one
            image_url = f"https://images-for-messenger.s3.eu-west-1.amazonaws.com/{key}"
            bot.send_photo(chat_id=user, photo=image_url)
            logger.info("Sent image URL to Facebook Messenger user")
        else:
            logger.info("Human not detected in the image")

    return 'File uploaded successfully', 200


@bot.message_handler(commands=['start'])
def start(message):
	bot.reply_to(message, "Say Hi! to SecureEye!")


# Handle incoming messages from Telegram
@bot.message_handler(content_types=['photo'])
def handle_message(message):
    logger.info(f"Received the photo from the user.")
    
    chat_id = message.chat.id
    logger.info(f"Got id.")

    fileID = message.photo[-1].file_id
    file_info = bot.get_file(fileID)
    image_bytes = bot.download_file(file_info.file_path)

    image_stream = BytesIO(image_bytes)

    # Open the image
    image = Image.open(image_stream)
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

        # Check if the user already exists
        user = chat_ids.search(UserQuery.ChatId == chat_id)
        if not user:
            # Create a new user if it does not exist
            chat_ids.insert({'ChatId': chat_id})
            logger.info("New user created.")

        # Assign the cameraID to the user
        chat_ids_camera.insert({'CameraId': camera_id, 'ChatId': chat_id})
        logger.info("Saved the user and camera id to the database.")

        s3.upload_file('db.json', 'images-for-messenger', 'db.json')
        logger.info("Uploaded the database to S3.")
    
        response = "Successfully registered your camera!"
    else:
        logger.info(f"Could not decode QR code")
        response = "Could not decode QR code. Please try again."

    os.remove("temp.png")  # Remove the local temporary file
    bot.send_message(chat_id=chat_id, text=response)
    logger.info("Sent the response.")


@app.route(f'/{BOT_FATHER_TOKEN}', methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200


# Run the Flask web application
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
