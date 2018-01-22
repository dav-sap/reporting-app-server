import os
from flask import Flask, send_from_directory, request
from flask_cors import CORS, cross_origin
import json
from pywebpush import webpush
from pyfcm import FCMNotification
from pymongo import MongoClient
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VAPID_PRIVATE_KEY = open(BASE_DIR + "/private_key.txt", "r+").readline().strip("\n")
VAPID_PUBLIC_KEY = open(BASE_DIR + "/public_key.txt", "r+").read().strip("\n")
VAPID_CLAIMS = {
    "sub": "mailto:sdwhat@europe.com"
}

MONGO_URL = os.environ.get('MONGODB_URI')
FCM_API_KEY = "AAAATWdiNVI:APA91bGWQD5T9IIJuIB-M7qsflpQjgjM55cZ7vI8lb7CuM-t6Eb-qweCIj92cgPBq0bVyC9KaT4Psuu019L7gQa7TWTd9raCNNjJB6ASAMMoWIvFRGSR59XaB-0cW0TPhPo-0AcbgbMf"
push_service = FCMNotification(api_key=FCM_API_KEY)

app = Flask(__name__)

mongo_client = MongoClient(MONGO_URL)
db = mongo_client.MembersData
CORS(app)


def create_admin(name, email, subscription_info, loc):
    data_message = {
        "title": "You are an Admin",
        "name": name,
        "email": email,
        "approved": True,
    }
    webpush(subscription_info, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS)
    print("No Admins. Making " + name + " an Admin!")
    db.Members.insert_one({
        "name": name,
        "email": email,
        "subscription": subscription_info,
        "loc": loc,
        "admin": True
    })


def send_push_msg_to_admins(name, email, loc, subscription_info):
    admins = db.Members.find({"admin": True})
    if admins and admins.count() > 0:
        admin_sent = False
        for doc in admins:
            print("ADMIN: " + str(doc))
            data_message = {
                "title": "User approval",
                "body": name + " , " + email + ", wants to register",
                "name": name,
                "email": email,
                "admin": True
            }
            try:
                webpush(doc["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS, timeout=10)
                admin_sent = True
            except Exception as e:
                db.Members.find_one_and_delete(doc)
        if admin_sent:
            db.awaitingMembers.insert_one({
                "name": name,
                "email": email,
                "subscription": subscription_info,
                "loc": loc,
            })
        else:
            create_admin(name, email, subscription_info, loc)
    else:
        create_admin(name, email, subscription_info, loc)


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


@app.route('/add_report', methods=['POST'])
def add_report():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys() and 'Status' in headers.keys() and 'Date' in headers.keys():
        db.Members.find_one_and_update({'name': headers['name'], 'email': headers['email']}, {'$push': {headers['status']: headers['date']}})
        return "report added"
    else:
        return "Wrong Headers", 403


@app.route('/deny_user', methods=['POST'])
def deny_user():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys():
        member = db.awaitingMembers.find_one_and_delete({'name': headers['name'], 'email': headers['email']})
        if member:
            data_message = {
                "title": "Your'e registration has been denied!",
                "name": member["name"],
                "email": member["email"],
                "approved": False,
            }
            webpush(member["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=VAPID_CLAIMS)
            return "user removed from waiting list"
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


@app.route('/register', methods=['POST'])
def register():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys() and 'Sub' in headers.keys():
        if db.Members.find({"email": headers['email'], 'name': headers['name']}).count() > 0:
            return "User already exists in DB", 403
        send_push_msg_to_admins(headers['name'],  headers['email'], 'JER', json.loads(headers['sub']))
        return "Waiting on Auth", 200
    else:
        return "Wrong Headers", 403


app.run(port=os.environ.get('PORT'))