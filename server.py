import os
from flask import Flask, send_from_directory, request
from flask_cors import CORS, cross_origin
import string
import random
import json
import uuid
import re
import sys
from pywebpush import webpush, WebPushException
from pyfcm import FCMNotification
from pymongo import MongoClient
from pymongo import ReturnDocument
from bson.json_util import loads
from bson.json_util import dumps
from dateutil.parser import parse
from passlib.hash import sha256_crypt
from datetime import datetime
from datetime import timedelta
from flask_mail import Mail
# from flask_mail import Message
push_service = None
connection = None
VAPID_PRIVATE_KEY = None
VAPID_PUBLIC_KEY = None
VAPID_CLAIMS = None
ADMIN_PASSWORD = None
if len(sys.argv) > 1 and sys.argv[1] == 'local':
    import LocalHostConst
    push_service = FCMNotification(api_key=LocalHostConst.FCM_API_KEY)
    connection = MongoClient(LocalHostConst.MONGO_URL)
    VAPID_PRIVATE_KEY = LocalHostConst.VAPID_PRIVATE_KEY
    VAPID_PUBLIC_KEY = LocalHostConst.VAPID_PUBLIC_KEY
    VAPID_CLAIMS = LocalHostConst.VAPID_CLAIMS
    ADMIN_PASSWORD = LocalHostConst.ADMIN_PASSWORD
else:
    push_service = FCMNotification(api_key=os.environ.get('FCM_API_KEY'))
    connection = MongoClient(os.environ.get('MONGODB_URI'))
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY')
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY')
    VAPID_CLAIMS = dict(os.environ.get('VAPID_CLAIMS'))
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
print (str(os.environ.get('FCM_API_KEY')))
print (str(os.environ.get('MONGODB_URI')))
print (str(VAPID_PRIVATE_KEY))
print (str(VAPID_PUBLIC_KEY))
print (str(VAPID_CLAIMS))
print (str(ADMIN_PASSWORD))
mail = Mail()

app = Flask(__name__)
mail.init_app(app)


db = connection['flex-app']
CORS(app)


def id_generator(size=10, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


@app.route('/push_to_all', methods=['POST'])
def push_to_all():
    headers = request.headers
    if 'Msg-Title' in headers.keys() and 'Msg-Body' in headers.keys():
        members = db.Members.find({})
        if members and members.count() > 0:
            for doc in members:

                    if len(doc["subscription"]) > 0:
                        data_message = {
                            "title": headers['Msg-Body'],
                            "body": headers['Msg-Body'],
                            "admin_message": True
                        }
                        for sub in doc["subscription"]:
                            try:
                                webpush(sub, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
                                        vapid_claims=VAPID_CLAIMS)
                            except WebPushException as ex:
                                print("subscription is offline")
                                db.Members.find_one_and_update({'email': re.compile(doc['email'], re.IGNORECASE)},
                                                               {"$pull": {"subscription": sub}})
            return "sending push", 200
        else:
            return "No Members", 400
    else:
        return "Wrong Headers", 403


def create_admin(email, subscription_info, loc):
    data_message = {
        "title": "You are an Admin",
        "email": email,
        "approved": True,
        "subscription": subscription_info,
    }
    if subscription_info:
        try:
            webpush(subscription_info, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,vapid_claims=VAPID_CLAIMS)
        except WebPushException as ex:
            print("Admin subscription is offline")
    print("No Admins. Making " + email + " an Admin!")
    member = {
        "email": email,
        "subscription": subscription_info,
        "loc": loc,
        "admin": True
    }
    db.Members.insert_one({
        "email": email,
        "subscription": subscription_info,
        "loc": loc,
        "admin": True
    })
    return member


@app.route('/forgot_password', methods=['POST'])
def forgot_password():
    return "sent", 200


@app.route('/send_push_testing', methods=['POST'])
def send_push_testing():

    admins = db.Members.find({"admin": True})
    if admins and admins.count() > 0:
        for doc in admins:
            print("ADMIN: " + str(doc))
            try:
                if doc["subscription"]:
                    for sub in doc["subscription"]:
                        data_message = {
                            "title": "Morning Report",
                            "body": "testing"
                        }
                        webpush(sub, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS, timeout=10)
            except WebPushException as ex:
                print (ex)
                print("Admin subscription is offline")
        return "success", 200
    else:
        return "no admins", 400


def send_push_msg_to_admins(email, loc, subscription_info, password):
    admins = db.Members.find({"admin": True})
    if admins and admins.count() > 0:
        for doc in admins:
            print("ADMIN: " + str(doc))
            try:
                if doc["subscription"]:
                    for sub in doc["subscription"]:
                        data_message = {
                            "title": "User approval",
                            "body":  email + ", wants to register",
                            "email": email,
                            "admin": True,
                            "name": email[:email.find("@")].replace(".", " ").title()
                        }
                        webpush(sub, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS, timeout=10)
            except WebPushException as ex:
                print("Admin subscription is offline")

        db.awaitingMembers.insert_one({
            "email": email,
            "subscription": subscription_info,
            "loc": loc,
            "password": password,
            "name": email[:email.find("@")].replace(".", " ").title()
        })
        return False
    else:
        return create_admin(email, subscription_info, loc)


@app.route('/cancel_await_member', methods=['POST'])
def cancel_await_member():
    headers = request.headers
    if 'Email' in headers.keys():
        member = db.awaitingMembers.find_one_and_delete({'email': re.compile(headers['email'], re.IGNORECASE)})
        if member:
            return "member removed", 200
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


def remove_time_zone(date):
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
        reports = []
        for member in members:
            if 'reports' in member.keys():
                for item in member['reports']:
                    start_dt = parse(remove_time_zone(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                    end_dt = parse(remove_time_zone(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                    if datetime.strptime(start_dt, '%d/%m/%Y') <= datetime.strptime(given_date, '%d/%m/%Y')  <= datetime.strptime(end_dt, '%d/%m/%Y'):
                        item['name'] = member['email'][:member['email'].find("@")].replace(".", " ").title()
                        reports.append(item)
        return dumps({'reports': reports}), 200
    else:
        return "Wrong Headers", 403


@app.route('/get_members_status_between_dates', methods=['GET'])
def get_members_status_between_dates():
    start_date_str = str(request.args.get('startdate'))
    end_date_str = str(request.args.get('enddate'))
    if start_date_str and end_date_str:
        given_start_date = parse(start_date_str).strftime('%d/%m/%Y')
        given_end_date = parse(end_date_str).strftime('%d/%m/%Y')
        if not datetime.strptime(given_start_date, '%d/%m/%Y') <= datetime.strptime(given_end_date, '%d/%m/%Y'):
            return "Wrong Headers", 403
        members = db.Members.find({})
        reports = []
        for member in members:
            if 'reports' in member.keys():
                for item in member['reports']:
                    start_dt = parse(remove_time_zone(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                    end_dt = parse(remove_time_zone(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                    if datetime.strptime(start_dt, '%d/%m/%Y') <= datetime.strptime(given_end_date,'%d/%m/%Y') and datetime.strptime(end_dt, '%d/%m/%Y') >= datetime.strptime(given_start_date, '%d/%m/%Y'):
                        item['name'] = member['email'][:member['email'].find("@")].replace(".", " ").title()
                        reports.append(item)
        return dumps({'reports': reports}), 200
    else:
        return "Wrong Headers", 403


@app.route('/get_all_members', methods=['GET'])
def get_all_members():
    members = db.Members.find({})
    members_to_return = []
    for member in members:
        members_to_return.append(member)
    return dumps({'members': members_to_return}), 200


@app.route('/get_awaiting_members', methods=['GET'])
def get_awaiting_members():
    members = db.awaitingMembers.find({})
    members_to_return = []
    for member in members:
        members_to_return.append(member)
    return dumps({'members': members_to_return}), 200


@app.route('/add_arriving', methods=['POST'])
def add_arriving():
    body_json = request.get_json()
    if 'name' in body_json.keys():
        if db.Arriving.find_one_and_update({"date": str(datetime.now().date())}, {"$push": {"members":body_json['name']}}):
            return "arriving added", 200
        else:
            db.Arriving.insert_one({"date": str(datetime.now().date()), "members": [body_json['name']]})
            return "arriving added", 200


@app.route('/get_arriving', methods=['GET'])
def get_arriving():
    arriving = db.Arriving.find_one({"date": str(datetime.now().date())})
    return dumps(arriving), 200


@app.route('/add_user', methods=['POST'])
def add_user():
    headers = request.headers
    if 'Email' in headers.keys():
        member = db.awaitingMembers.find_one({'email': re.compile(headers['email'], re.IGNORECASE)})
        if member:
            db.awaitingMembers.find_one_and_delete({'email': headers['email']})

            db.Members.insert_one({
                "name": member["name"],
                "email": member['email'],
                "subscription": [member['subscription']],
                "loc": member['loc'],
                "password": member['password']
             })
            try:
                if member["subscription"]:
                    data_message = {
                        "title": "Your'e Approved!",
                        "email": member["email"],
                        "name": member["name"],
                        "body":  "use this app wisely",
                        "admin": False,
                        "approved": True,
                        "loc": member['loc'],
                        "sub": member["subscription"],
                    }
                    webpush(member["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS)
            except WebPushException as ex:
                print("user subscription is offline")
                db.Members.find_one_and_update({'email': member['email']},{"$set": {"subscription": []}})
            return "User added"
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


@app.route('/check_subscription', methods=['POST'])
def check_subscription():
    headers = request.headers
    if 'Email' in headers.keys() and 'Sub' in headers.keys():
        member = db.Members.find_one({'email': re.compile(headers['email'], re.IGNORECASE)})
        if member:
            sub_from_client = loads(headers['sub'])

            for sub in member["subscription"]:
                if sub == sub_from_client:
                    return "subscription exists", 200
            return "No subscription", 401
        else:
            return "No member", 401
    else:
        return "Wrong Headers", 403


@app.route('/change_profile', methods={'POST'})
def change_profile():
    body_json = request.get_json()
    if 'oldEmail' in body_json.keys() and 'newEmail' in body_json.keys() \
            and 'oldPass' in body_json.keys() and 'newPass' in body_json.keys() and 'nickname' in body_json.keys():
        member = db.Members.find_one({'email': body_json['oldEmail']})
        if member:
            if sha256_crypt.verify(body_json['oldPass'], member['password']) or body_json['oldPass'] == ADMIN_PASSWORD:
                if body_json['newPass'] != "":
                    member['password'] = sha256_crypt.hash(body_json['newPass'])
                if body_json['oldEmail'] != body_json['newEmail']:
                    member['email'] = body_json['newEmail']
                member['name'] = body_json['nickname']
                db.Members.save(member)
                return "Member updated",  200
            else:
                return dumps({'msg': "Password Incorrect"}), 401
        else:
            return dumps({'msg': "No such Member"}), 401
    else:
        return "Wrong Headers", 403


@app.route('/add_subscription', methods=['POST'])
def add_subscription():
    headers = request.headers
    if 'Email' in headers.keys() and 'Sub' in headers.keys():
        member = db.Members.find_one_and_update({'email': headers['email']},{"$push": {"subscription": loads(headers['sub'] if headers['sub'] else {})}})
        if member:
            return "subscription added", 200
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/remove_subscription', methods=['POST'])
def remove_subscription():
    headers = request.headers
    if 'Email' in headers.keys() and 'Sub' in headers.keys():
        member = db.Members.find_one_and_update({'email': headers['email']},{"$pull": {"subscription": loads(headers['sub'] if headers['sub'] else {})}})
        if member:
            return "Removed subscription", 200
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/remove_report', methods=['POST'])
def remove_report():
    body_json = request.get_json()
    if 'email' in body_json.keys() and 'report_id' in body_json.keys():
        member = db.Members.find_one_and_update({'email' : body_json['email']}, {'$pull': {'reports': {'_id':body_json['report_id']}}}, return_document=ReturnDocument.AFTER)
        if member:
            return "Report Removed", 200
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/get_user_reports', methods=['GET'])
def get_user_reports():
    headers = request.headers
    if 'Email' in headers.keys():
        member = db.Members.find_one({"email": re.compile(headers['email'], re.IGNORECASE)})
        if member:
            list_to_ret = member['reports'] if 'reports' in member.keys() else []
            return dumps(list_to_ret), 200
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/logout', methods=['POST'])
def logout():
    headers = request.headers
    if 'Email' in headers.keys() and 'Sub' in headers.keys():
        member = db.Members.find_one_and_update({"email": re.compile(headers['email'], re.IGNORECASE)},
                                           {"$pull": {"subscription": loads(headers['Sub'])}},  return_document=ReturnDocument.AFTER)
        if member:
            return "Logout Successful", 200
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/verify_await_user', methods=['POST'])
def verify_await_user():
    body_json = request.get_json()
    if 'email' in body_json.keys():
        member = db.awaitingMembers.find_one({"email": body_json['email']})
        if member:
            return dumps({'info': "user verified", 'member': dumps(member)}), 200

        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403

@app.route('/verify_user', methods=['POST'])
def verify_user():
    body_json = request.get_json()
    if 'email' in body_json.keys():
        member = db.Members.find_one({"email": body_json['email']})
        if member:
            return dumps({'info': "user verified", 'member': dumps(member)}), 200

        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403

@app.route('/add_report', methods=['POST'])
def add_report():
    body_json = request.get_json()
    if 'status' in body_json.keys() and 'startDate' in body_json.keys() and 'endDate' in body_json.keys() \
            and 'note' in body_json.keys() and 'repeat' in body_json.keys() and 'statusDesc' in body_json.keys():
        member = db.Members.find_one({'email' : re.compile(body_json['email'], re.IGNORECASE)})
        if member:
            member_status = member['reports'] if 'reports' in member.keys() else []
            start_date = datetime.strptime(str(body_json['startDate']), '%Y-%m-%dT%H:%M')
            end_date = datetime.strptime(str(body_json['endDate']), '%Y-%m-%dT%H:%M')
            report_id = uuid.uuid4()
            for i in range(0, int(body_json['repeat']) + 1):
                new_start_date = start_date + timedelta(weeks=i)
                new_end_date = end_date + timedelta(weeks=i)
                member_status.append({'startDate': new_start_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ'), 'endDate': new_end_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),'statusDescription': body_json['statusDesc'],
                                      'note': body_json['note'], '_id': str(report_id), 'status': body_json['status'], 'recurring': True if int(body_json['repeat']) > 0 else False})
            db.Members.find_one_and_update({'email': re.compile(body_json['email'], re.IGNORECASE)},{'$set': {'reports':member_status}})
            return "report added", 200
        else:
            return "User not found", 403
    else:
        return "Wrong Headers", 403


@app.route('/deny_user', methods=['POST'])
def deny_user():
    headers = request.headers
    if 'Email' in headers.keys():
        member = db.awaitingMembers.find_one_and_delete({'email': re.compile(headers['email'], re.IGNORECASE)})
        if member:
            try:
                if member["subscription"]:
                    data_message = {
                        "title": "Approval denied!",
                        "body": member["email"] + ", your registration has been denied",
                        "email": member["email"],
                        "approved": False,
                    }
                    webpush(member["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
                            vapid_claims=VAPID_CLAIMS)
            except WebPushException as ex:
                print("user subscription is offline")
                return "user removed from waiting list", 200
            return "user removed from waiting list", 200
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


@app.route('/remove_member', methods=['POST'])
def remove_member():
    headers = request.headers
    if 'Email' in headers.keys():
        member = db.Members.find_one_and_delete({'email': re.compile(headers['email'], re.IGNORECASE)})
        if member:
            try:
                if member["subscription"]:
                    data_message = {
                        "title": "Remove Member",
                        "body":  member["email"] + ", your membership has been removed, please sign up",
                        "email": member["email"],
                        "approved": False,
                    }
                    webpush(member["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
                            vapid_claims=VAPID_CLAIMS)
            except WebPushException as ex:
                print("user subscription is offline")
                return "member removed", 200
            return "member removed", 200
        else:
            return "No member found in member list", 404
    else:
        return "Wrong Headers", 403


@app.route('/register', methods=['POST'])
def register():
    headers = request.headers
    if 'Email' in headers.keys() and 'Sub' in headers.keys() and 'Loc' in headers.keys() and 'Password' in headers.keys():
        if db.Members.find({"email": re.compile(headers['email'], re.IGNORECASE)}).count() > 0:
            return "User already taken", 403

        member = send_push_msg_to_admins(headers['email'], headers['loc'],loads(headers['sub'] if headers['sub'] else {}), sha256_crypt.hash(headers['password']))
        if not member:
            return dumps({'info': "Waiting for Admin Approval"}), 202
        else:
            return dumps({'info': "You are an Admin", 'member': member}), 200
    else:
        return "Wrong Info", 403


@app.route('/login', methods=['POST'])
def login():
    headers = request.headers
    if 'Password' in headers.keys() and 'Email' in headers.keys() and 'Sub' in headers.keys():
        member = db.Members.find_one({"email": re.compile(headers['email'], re.IGNORECASE)})
        if member:
            if sha256_crypt.verify(headers['password'], member['password']) or headers['password'] == ADMIN_PASSWORD:
                if loads(headers['sub']) == {} or loads(headers['sub']) in member['subscription']:
                    return dumps({'info': "user logged in", 'member': member}), 200
                else:
                    member = db.Members.find_one_and_update({"email": re.compile(headers['email'], re.IGNORECASE)}, {"$push": {"subscription": loads(headers['sub'])}} , return_document=ReturnDocument.AFTER)
                    # member.pop('_id', None)
                    return dumps({'info': "user subscription updated", 'member': member}), 200
            else:
                return "Login not successful", 401
        else:
            return "Login not successful", 401
    else:
        return "Wrong Headers", 400


@app.route('/test_pass', methods=['POST'])
def test_pass():
    body_json = request.get_json()
    hash = sha256_crypt.hash(body_json['pass'])
    member = db.Members.find_one_and_update({"name": 'Q'}, {"$set": {'password': hash}})

    return "success", 200

@app.route('/verify_pass', methods=['POST'])
def verify_pass():
    body_json = request.get_json()
    member = db.Members.find_one({"name": 'W'})
    if member and member['password']:
        member['pass'] = "2"
        db.Members.save(member)
        return str(sha256_crypt.verify(body_json['pass'], member['password'])), 200
    else:
        return "success", 500


    return "success", 200

port = 3141
if os.environ.get('PORT'):
    port = int(os.environ.get('PORT'))
app.run(port=port, host='0.0.0.0')

