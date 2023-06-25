from flask import Flask, request
import logging

app = Flask(__name__)

# Create a logger object
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)  # Set log level to INFO. Change it to DEBUG, ERROR, WARN as per your requirement.

# Route for uploading image
@app.route('/upload', methods=['POST'])
def uploadImage():
    logger.info("Received a request.")
    logger.info(f"Request headers: {request.headers}")
    logger.info(f"Request data: {request.get_data()}")

    # Check if the request contains the 'img' field
    if 'img' in request.files:
        logger.info("Image received successfully")
    else:
        logger.info("Image not found in the request")

    return 'Success', 200

# Run the Flask application
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
