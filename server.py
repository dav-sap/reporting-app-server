import os
from flask import Flask, send_from_directory, request
from flask_cors import CORS, cross_origin
import json
import uuid
from pywebpush import webpush, WebPushException
from pyfcm import FCMNotification
from pymongo import MongoClient
from pymongo import ReturnDocument
from bson.json_util import loads
from bson.json_util import dumps
from dateutil.parser import parse
import datetime

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
    if subscription_info:
        try:
            webpush(subscription_info, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,vapid_claims=VAPID_CLAIMS)
        except WebPushException as ex:
            print("Admin subscription is offline")
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
            try:
                if doc["subscription"]:
                    data_message = {
                        "title": "User approval",
                        "body": name + " , " + email + ", wants to register",
                        "name": name,
                        "email": email,
                        "admin": True
                    }
                    webpush(doc["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS, timeout=10)
            except WebPushException as ex:
                print("Admin subscription is offline")
                db.Members.find_one_and_update({'name': doc['name'], 'email': doc['email']}, {"$set": {"subscription": {}}})

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


def removeTZ(date):
    if date[len(date) - 1] == ")":
        return date[:date.rfind("(")]
    else:
        return date


@app.route('/get_members_status_by_date', methods=['GET'])
def get_members_status_by_date():
    date = str(request.args.get('date'))
    if date:
        given_date = parse(date).strftime('%d/%m/%Y')
        members = db.Members.find({})
        ooo = []
        wfh = []
        sick = []
        for member in members:
            if 'OOO' in member.keys():
                for item in member['OOO']:
                    start_dt = parse(removeTZ(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                    end_dt = parse(removeTZ(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                    if start_dt <= given_date <= end_dt:
                        item['name'] = member['name']
                        ooo.append(item)
            if 'WFH' in member.keys():
                for item in member['WFH']:
                    start_dt = parse(removeTZ(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                    end_dt = parse(removeTZ(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                    if start_dt <= given_date <= end_dt:
                        item['name'] = member['name']
                        wfh.append(item)
            if 'SICK' in member.keys():
                for item in member['SICK']:
                    start_dt = parse(removeTZ(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                    end_dt = parse(removeTZ(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                    if start_dt <= given_date <= end_dt:
                        item['name'] = member['name']
                        sick.append(item)
        return dumps({'OOO': ooo, 'WFH': wfh, 'SICK': sick}), 200
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
            try:
                if member["subscription"]:
                    data_message = {
                        "title": "Your'e Approved!",
                        "name": member["name"],
                        "email": member["email"],
                        "body":  member["name"] + " , " + member["email"] + ", have has approved",
                        "admin": False,
                        "approved": True,
                        "sub": member["subscription"],
                    }
                    webpush(member["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS)
            except WebPushException as ex:
                print("user subscription is offline")
                db.Members.find_one_and_update({'name': member['name'], 'email': member['email']},{"$set": {"subscription": {}}})
            return "User added"
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


@app.route('/remove_report', methods=['POST'])
def remove_report():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys() and 'Report-Id' in headers.keys() and 'Status' in headers.keys():
        id_obj = loads(headers['Report-Id'])
        member = db.Members.find_one_and_update({'name': headers['name']}, {'$pull': {headers['status']: {'_id':id_obj }}}, return_document=ReturnDocument.AFTER)
        if member:
            return "Report Removed", 200
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/get_user_reports', methods=['GET'])
def get_user_reports():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys():
        member = db.Members.find_one({"email": headers['email'], 'name': headers['name']})
        if member:
            return dumps({'OOO': member['OOO'] if 'OOO' in member.keys() else [],
                               'WFH':  member['WFH'] if 'WFH' in member.keys() else [],
                               'SICK':  member['SICK'] if 'SICK' in member.keys() else []}), 200
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
            if not member['subscription'] or member['subscription'] == json.loads(headers['sub']):
                return dumps({'info': "user verified"}), 200
            else:
                member = db.Members.find_one_and_update({'name': headers['name'], "email": headers['email']}, {"$set": {"subscription": loads(headers['sub'])}} , return_document=ReturnDocument.AFTER)
                # member.pop('_id', None)
                return dumps({'info': "user subscription updated", member: member}), 202
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/add_report', methods=['POST'])
def add_report():
    headers = request.headers
    if 'Name' in headers.keys() and 'Status' in headers.keys() and 'Startdate' in headers.keys() and 'Enddate' in headers.keys() and 'Note' in headers.keys():
        member = db.Members.find_one_and_update({'name': headers['name']}, {'$push': {headers['status']: {'startDate': headers['startdate'], 'endDate': headers['enddate'], 'note': headers['note'],'_id': uuid.uuid4()}}}, return_document=ReturnDocument.AFTER)
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
            try:
                if member["subscription"]:
                    data_message = {
                        "title": "Approval denied!",
                        "body": member["name"] + " , " + member["email"] + ", your registration has been denied",
                        "name": member["name"],
                        "email": member["email"],
                        "approved": False,
                    }
                    webpush(member["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
                            vapid_claims=VAPID_CLAIMS)
            except WebPushException as ex:
                print("user subscription is offline")
                db.Members.find_one_and_update({'name': member['name'], 'email': member['email']}, {"$set": {"subscription": {}}})
                return "user removed from waiting list", 200
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

        member = send_push_msg_to_admins(headers['name'],  headers['email'], headers['loc'],loads(headers['sub'] if headers['sub'] else {}))
        if not member:
            return dumps({'info': "Waiting for Admin Approval"}), 202
        else:
            return dumps({'info': "You are an Admin", 'member': member}), 200
    else:
        return "Wrong Headers", 403


@app.route('/login', methods=['POST'])
def login():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys() and 'Sub' in headers.keys():
        member = db.Members.find_one({"email": headers['email'], 'name': headers['name']})
        if member:
            if member['subscription'] == headers['sub']:
                return dumps({'info': "user logged in", 'member': member}), 200
            else:
                member = db.Members.find_one_and_update({'name': headers['name'], "email": headers['email']}, {"$set": {"subscription": loads(headers['sub'])}} , return_document=ReturnDocument.AFTER)
                # member.pop('_id', None)
                return dumps({'info': "user subscription updated", 'member': member}), 200
        else:
            return "Login not successful", 401
    else:
        return "Wrong Headers", 400


port = 3141
if os.environ.get('PORT'):
    port = int(os.environ.get('PORT'))
app.run(port=port, host='0.0.0.0')
