import requests

url = "https://secureeye.herokuapp.com/upload"

# Open an image file in binary mode
with open('/Users/jakubsiekiera/Downloads/25percent4x4.png', 'rb') as f:
    file_data = f.read()

# Send a POST request to the server
response = requests.post(url, data=file_data)

# Print the response from the server
print(response.text)
