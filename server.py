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
from datetime import datetime
# from apscheduler.schedulers.background import BackgroundScheduler
# sched = BackgroundScheduler()
# sched.start()
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


# @sched.scheduled_job('cron', day_of_week='sun,mon,tue,wed,thu',hour=9, minute=0, timezone="Israel", second=10)
# def daily_update():
#     members = db.Members.find({})
#     if members and members.count() > 0:
#         for doc in members:
#             try:
#                 if doc["subscription"]:
#                     data_message = {
#                         "title": "Morning Report",
#                         "body": "Morning, What are u up to today?",
#                     }
#                     webpush(doc["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
#                             vapid_claims=VAPID_CLAIMS, timeout=10)
#             except WebPushException as ex:
#                 print("subscription is offline")
#                 db.Members.find_one_and_update({'name': doc['name'], 'email': doc['email']},
#                                                {"$set": {"subscription": {}}})


@app.route('/push_to_all', methods=['POST'])
def push_to_all():
    headers = request.headers
    if 'Msg-Title' in headers.keys() and 'Msg-Body' in headers.keys():
        members = db.Members.find({})
        if members and members.count() > 0:
            for doc in members:
                try:
                    if doc["subscription"]:
                        data_message = {
                            "title": headers['Msg-Body'],
                            "body": headers['Msg-Body'],
                            "admin_message": True
                        }
                        webpush(doc["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
                                vapid_claims=VAPID_CLAIMS)
                except WebPushException as ex:
                    print("subscription is offline")
                    db.Members.find_one_and_update({'name': doc['name'], 'email': doc['email']},
                                                   {"$set": {"subscription": {}}})
            return "sending push", 200
        else:
            return "No Members", 400
    else:
        return "Wrong Headers", 403


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

        db.awaitingMembers.insert_one({
            "name": name,
            "email": email,
            "subscription": subscription_info,
            "loc": loc,
        })
        return False
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
        ooo = []
        wf = []
        sick = []
        for member in members:
            if 'OOO' in member.keys():
                for item in member['OOO']:
                    start_dt = parse(remove_time_zone(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                    end_dt = parse(remove_time_zone(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                    if datetime.strptime(start_dt, '%d/%m/%Y') <= datetime.strptime(given_date, '%d/%m/%Y')  <= datetime.strptime(end_dt, '%d/%m/%Y'):
                        item['name'] = member['name']
                        ooo.append(item)
            if 'WF' in member.keys():
                for item in member['WF']:
                    start_dt = parse(remove_time_zone(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                    end_dt = parse(remove_time_zone(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                    if datetime.strptime(start_dt, '%d/%m/%Y') <= datetime.strptime(given_date, '%d/%m/%Y') <= datetime.strptime(end_dt, '%d/%m/%Y'):
                        item['name'] = member['name']
                        wf.append(item)
            if 'SICK' in member.keys():
                for item in member['SICK']:
                    start_dt = parse(remove_time_zone(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                    end_dt = parse(remove_time_zone(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                    if datetime.strptime(start_dt, '%d/%m/%Y') <= datetime.strptime(given_date, '%d/%m/%Y') <= datetime.strptime(end_dt, '%d/%m/%Y'):
                        item['name'] = member['name']
                        sick.append(item)
        return dumps({'OOO': ooo, 'WF': wf, 'SICK': sick}), 200
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
        ooo = []
        wf = []
        sick = []
        for member in members:
            if 'OOO' in member.keys():
                for item in member['OOO']:
                    start_dt = parse(remove_time_zone(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                    end_dt = parse(remove_time_zone(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                    if datetime.strptime(start_dt, '%d/%m/%Y') <= datetime.strptime(given_start_date, '%d/%m/%Y') and datetime.strptime(end_dt, '%d/%m/%Y') >= datetime.strptime(given_end_date, '%d/%m/%Y'):
                        item['name'] = member['name']
                        ooo.append(item)
            if 'WF' in member.keys():
                for item in member['WF']:
                    start_dt = parse(remove_time_zone(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                    end_dt = parse(remove_time_zone(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                    if datetime.strptime(start_dt, '%d/%m/%Y') <= datetime.strptime(given_start_date,'%d/%m/%Y') and datetime.strptime(end_dt, '%d/%m/%Y') >= datetime.strptime(given_end_date, '%d/%m/%Y'):
                        item['name'] = member['name']
                        wf.append(item)
            if 'SICK' in member.keys():
                for item in member['SICK']:
                    start_dt = parse(remove_time_zone(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                    end_dt = parse(remove_time_zone(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                    if datetime.strptime(start_dt, '%d/%m/%Y') <= datetime.strptime(given_start_date,'%d/%m/%Y') and datetime.strptime(end_dt, '%d/%m/%Y') >= datetime.strptime(given_end_date, '%d/%m/%Y'):
                        item['name'] = member['name']
                        sick.append(item)
        return dumps({'OOO': ooo, 'WF': wf, 'SICK': sick}), 200
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


@app.route('/check_subscription', methods=['POST'])
def check_subscription():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys():
        member = db.Members.find_one({'name': headers['name'], 'email': headers['email']})
        if member:
            if member["subscription"]:
                return "subscription exists", 200
            else:
                return "No subscription", 401
        else:
            return "No member", 401
    else:
        return "Wrong Headers", 403


@app.route('/add_subscription', methods=['POST'])
def add_subscription():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys() and 'Sub' in headers.keys():
        member = db.Members.find_one_and_update({'name': headers['name'], 'email': headers['email']},{"$set": {"subscription": loads(headers['sub'] if headers['sub'] else {})}})
        if member:
            return "Removed subscription", 200
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/remove_subscription', methods=['POST'])
def remove_subscription():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys():
        member = db.Members.find_one_and_update({'name': headers['name'], 'email': headers['email']},{"$set": {"subscription": {}}})
        if member:
            return "Removed subscription", 200
        else:
            return "No such member", 401
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
                               'WF':  member['WF'] if 'WF' in member.keys() else [],
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
    body_json = request.get_json()
    if 'name' in body_json.keys() and 'email' in body_json.keys() and 'sub' in body_json.keys():
        member = db.Members.find_one({"email": body_json['email'], 'name': body_json['name']})
        if member:
            if not member['subscription'] or member['subscription'] == json.loads(body_json['sub']):
                return json.dumps({'info': "user verified", 'member': dumps(member)}), 200
            else:
                member = db.Members.find_one_and_update({'name': body_json['name'], "email": body_json['email']}, {"$set": {"subscription": loads(body_json['sub'])}} , return_document=ReturnDocument.AFTER)
                return json.dumps({'info': "user subscription updated", member: dumps(member)}), 202
        else:
            return "No such member", 401
    else:
        return "Wrong Headers", 403


@app.route('/add_report', methods=['POST'])
def add_report():
    body_json = request.get_json()
    if 'name' in body_json.keys() and 'status' in body_json.keys() and 'startDate' in body_json.keys() and 'endDate' in body_json.keys() and 'note' in body_json.keys():
        member = db.Members.find_one_and_update({'name': body_json['name']}, {'$push': {body_json['status']: {'startDate': body_json['startDate'], 'endDate': body_json['endDate'], 'note': body_json['note'],'_id': uuid.uuid4()}}}, return_document=ReturnDocument.AFTER)
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
            return "user removed from waiting list", 200
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


@app.route('/remove_member', methods=['POST'])
def remove_member():
    headers = request.headers
    if 'Name' in headers.keys() and 'Email' in headers.keys():
        member = db.Members.find_one_and_delete({'name': headers['name'], 'email': headers['email']})
        if member:
            try:
                if member["subscription"]:
                    data_message = {
                        "title": "Remove Member",
                        "body": member["name"] + " , " + member["email"] + ", your have been removed, please sign up",
                        "name": member["name"],
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
    if 'Name' in headers.keys() and 'Email' in headers.keys() and 'Sub' in headers.keys() and 'Loc' in headers.keys():
        if db.Members.find({"email": headers['email'], 'name': headers['name']}).count() > 0:
            return "User already taken", 403

        member = send_push_msg_to_admins(headers['name'],  headers['email'], headers['loc'],loads(headers['sub'] if headers['sub'] else {}))
        if not member:
            return dumps({'info': "Waiting for Admin Approval"}), 202
        else:
            return dumps({'info': "You are an Admin", 'member': member}), 200
    else:
        return "Wrong Info", 403


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

