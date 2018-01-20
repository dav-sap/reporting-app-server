import os, sys
from flask import Flask, send_from_directory, request
from flask_cors import CORS, cross_origin
import json
from pywebpush import webpush
# from flask_pyfcm import FCM
from pyfcm import FCMNotification
from pymongo import MongoClient

VAPID_PRIVATE_KEY = open(os.path.dirname(sys.argv[0]) + "/private_key.txt", "r+").readline().strip("\n")
VAPID_PUBLIC_KEY = open(os.path.dirname(sys.argv[0]) + "/public_key.txt", "r+").read().strip("\n")
VAPID_CLAIMS = {
    "sub": "mailto:davidsaper2@gmail.com"
}

APP_BUILD_FOLDER = 'pwa-experiment/build'

FCM_API_KEY = "AAAATWdiNVI:APA91bGWQD5T9IIJuIB-M7qsflpQjgjM55cZ7vI8lb7CuM-t6Eb-qweCIj92cgPBq0bVyC9KaT4Psuu019L7gQa7TWTd9raCNNjJB6ASAMMoWIvFRGSR59XaB-0cW0TPhPo-0AcbgbMf"
push_service = FCMNotification(api_key=FCM_API_KEY)

app = Flask(__name__, static_folder=APP_BUILD_FOLDER )

mongo_client = MongoClient('localhost:3142')
db = mongo_client.MembersData
CORS(app)


def send_push_msg_to_admins(name, email, loc, subscription_info):
    db.awaitingMembers.insert_one({
            "name": name,
            "email": email,
            "subscription": subscription_info,
            "loc": loc,
        })
    for doc in db.Members.find({"admin": True}):
        print("ADMIN: " + str(doc))

        data_message = {
            "title": "User approval",
            "body": name + " , " + email + ", wants to register",
            "name": name,
            "email": email,
            "admin": True
        }
        webpush(doc["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS)


@app.route('/add_user', methods=['POST'])
def add_user():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys():
        member = db.awaitingMembers.find_one({'name': headers['name'], 'email': headers['email']})
        if member:
            db.awaitingMembers.find_one_and_delete({'name': headers['name'], 'email': headers['email']})
            db.Members.insert_one(member)
            data_message = {
                "title": "Your'e Approved!",
                "name": member["name"],
                "email": member["email"],
                "admin": False,
                "approved": True,
            }
            webpush(member["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS)
            return "User added"
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


@app.route('/deny_user', methods=['POST'])
def deny_user():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys():
        member = db.awaitingMembers.find_one_and_delete({'name': headers['name'], 'email': headers['email']})
        if member:
            return "user removed from waiting list"
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


@app.route('/register', methods=['POST'])
def register():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys() and 'Sub' in headers.keys():
        if len(db.Members.find({"email": headers['email'], 'name': headers['name']})) > 0:
            return "User already exists in DB", 403
        send_push_msg_to_admins(headers['name'],  headers['email'], 'JER', json.loads(headers['sub']))
        return "Waiting on Auth", 200
    else:
        return "Wrong Headers", 403


if __name__ == '__main__':
    app.run(use_reloader=True, port=3141, threaded=True)