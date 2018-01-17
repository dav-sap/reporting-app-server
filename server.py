import os
from flask import Flask, send_from_directory, request
from flask_cors import CORS, cross_origin
from pymongo import MongoClient
APP_BUILD_FOLDER = 'pwa-experiment/build'

app = Flask(__name__, static_folder=APP_BUILD_FOLDER )
client = MongoClient('localhost:3142')
db = client.MembersData
CORS(app)


# Serve React App
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path == "":
        return send_from_directory(APP_BUILD_FOLDER, 'index.html')
    else:
        if os.path.exists(APP_BUILD_FOLDER + path):
            return send_from_directory(APP_BUILD_FOLDER, path)
        else:
            return send_from_directory(APP_BUILD_FOLDER, 'index.html')


@app.route('/add_user')
def add_user():
    headers = request.headers
    if 'Pass' in headers.keys() and 'Name' in headers.keys() and 'Loc' in headers.keys():
        if headers['pass'] == "qwQW!@12":
            db.Members.insert_one(
                {
                    "name": headers['name'],
                    "loc": headers['loc']
                })
            return "user added"
        else:
            return "password wrong", 404
    else:
        return "Wrong Headers", 403


if __name__ == '__main__':
    app.run(use_reloader=True, port=3141, threaded=True)