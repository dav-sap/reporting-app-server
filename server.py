import os
from flask import Flask, send_from_directory, request
from flask_cors import CORS, cross_origin
import json
from pywebpush import webpush
from pyfcm import FCMNotification
from pymongo import MongoClient
from pymongo import ReturnDocument

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VAPID_PRIVATE_KEY = open(BASE_DIR + "/private_key.txt", "r+").readline().strip("\n")
VAPID_PUBLIC_KEY = open(BASE_DIR + "/public_key.txt", "r+").read().strip("\n")
VAPID_CLAIMS = {
    "sub": "mailto:sdwhat@europe.com"
}
MONGO_URL = "mongodb://davOwner:1234@ds211588.mlab.com:11588/flex-app"
if os.environ.get('MONGODB_URI'):
    MONGO_URL =os.environ.get('MONGODB_URI')
FCM_API_KEY = "AAAATWdiNVI:APA91bGWQD5T9IIJuIB-M7qsflpQjgjM55cZ7vI8lb7CuM-t6Eb-qweCIj92cgPBq0bVyC9KaT4Psuu019L7gQa7TWTd9raCNNjJB6ASAMMoWIvFRGSR59XaB-0cW0TPhPo-0AcbgbMf"
push_service = FCMNotification(api_key=FCM_API_KEY)

app = Flask(__name__)

connection = MongoClient(MONGO_URL)
db = connection['flex-app']
CORS(app)


def create_admin(name, email, subscription_info, loc):
    data_message = {
        "title": "You are an Admin",
        "name": name,
        "email": email,
        "approved": True,
        "subscription": subscription_info,
    }
    webpush(subscription_info, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS)
    print("No Admins. Making " + name + " an Admin!")
    member = {
        "name": name,
        "email": email,
        "subscription": subscription_info,
        "loc": loc,
        "admin": True
    }
    db.Members.insert_one({
        "name": name,
        "email": email,
        "subscription": subscription_info,
        "loc": loc,
        "admin": True
    })
    return member


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
            if doc["subscription"]:
                webpush(doc["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS, timeout=10)
            admin_sent = True
        if admin_sent:
            db.awaitingMembers.insert_one({
                "name": name,
                "email": email,
                "subscription": subscription_info,
                "loc": loc,
            })
            return False
        else:
            return create_admin(name, email, subscription_info, loc)

    else:
        return create_admin(name, email, subscription_info, loc)


@app.route('/cancel_await_member', methods=['POST'])
def cancel_await_member():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys():
        member = db.awaitingMembers.find_one_and_delete({'name': headers['name'], 'email': headers['email']})
        if member:
            return "member removed", 200
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


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
                "sub": member["subscription"],
            }
            webpush(member["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS)
            return "User added"
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


@app.route('/get_user_reports', methods=['GET'])
def get_user_reports():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys():
        member = db.Members.find_one({"email": headers['email'], 'name': headers['name']})
        if member:
            return json.dumps({'OOO': member['OOO'],'WFH': member['WFH'], 'SICK': member['SICK']}), 200
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/logout', methods=['POST'])
def logout():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys():
        member = db.Members.find_one_and_update({"email": headers['email'], 'name': headers['name']}, {"$set": {"subscription": {}}}, return_document=ReturnDocument.AFTER)
        if member:
            return "Logout Successful", 200
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/verify_user', methods=['POST'])
def verify_user():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys() and 'Sub' in headers.keys():
        member = db.Members.find_one({"email": headers['email'], 'name': headers['name']})
        if member:
            if member['subscription'] == json.loads(headers['sub']):
                return json.dumps({'info': "user verified"}), 200
            else:
                member = db.Members.find_one_and_update({'name': headers['name'], "email": headers['email']}, {"$set": {"subscription": json.loads(headers['sub'])}} , return_document=ReturnDocument.AFTER)
                member.pop('_id', None)
                return json.dumps({'info': "user subscription updated", member: member}), 202
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/add_report', methods=['POST'])
def add_report():
    headers = request.headers
    if 'Name' in headers.keys() and 'Status' in headers.keys() and 'Startdate' in headers.keys() and 'Enddate' in headers.keys():
        member = db.Members.find_one_and_update({'name': headers['name']}, {'$push': {headers['status']: {'startDate': headers['startdate'], 'endDate': headers['enddate']}}}, return_document=ReturnDocument.AFTER)
        if member:
            return "report added", 200
        else:
            return "User not found", 403
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
    if 'Name' in headers.keys() and 'Email' in headers.keys() and 'Sub' in headers.keys() and 'Loc' in headers.keys():
        if db.Members.find({"email": headers['email'], 'name': headers['name']}).count() > 0:
            return "User already taken", 403
        member = send_push_msg_to_admins(headers['name'],  headers['email'], headers['loc'], json.loads(headers['sub']))
        if not member:
            return json.dumps({'info': "Waiting for Admin Approval"}), 202
        else:
            return json.dumps({'info': "You are an Admin", 'member': member}), 200
    else:
        return "Wrong Headers", 403


@app.route('/login', methods=['POST'])
def login():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys() and 'Sub' in headers.keys():
        member = db.Members.find_one({"email": headers['email'], 'name': headers['name']})
        if member:
            if member['subscription'] == headers['sub']:
                return json.dumps({'info': "user logged in", 'member': member}), 200
            else:
                member = db.Members.find_one_and_update({'name': headers['name'], "email": headers['email']}, {"$set": {"subscription": json.loads(headers['sub'])}} , return_document=ReturnDocument.AFTER)
                member.pop('_id', None)
                return json.dumps({'info': "user subscription updated", 'member': member}), 200
        else:
            return "Login not successful", 401
    else:
        return "Wrong Headers", 400


port = 3141
if os.environ.get('PORT'):
    print (os.environ.get('PORT'))
    port = int(os.environ.get('PORT'))
app.run(port=port, host='0.0.0.0')
