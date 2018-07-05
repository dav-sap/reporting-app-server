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
from bson.objectid import ObjectId
from bson.json_util import loads
from bson.json_util import dumps
from dateutil.parser import parse
from passlib.hash import sha256_crypt
from datetime import datetime
from datetime import timedelta
# from flask_mail import Mail, Message
from flask_httpauth import HTTPBasicAuth
from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools

auth = HTTPBasicAuth()

calendar_api_service = None
push_service = None
connection = None
VAPID_PRIVATE_KEY = None
VAPID_PUBLIC_KEY = None
VAPID_CLAIMS = None
ADMIN_PASSWORD = None
GOOGLE_API_CALENDER_CREDS = None
if len(sys.argv) > 1 and sys.argv[1] == '--local':
    import LocalHostConst
    push_service = FCMNotification(api_key=LocalHostConst.FCM_API_KEY)
    connection = MongoClient(LocalHostConst.MONGO_URL)
    VAPID_PRIVATE_KEY = LocalHostConst.VAPID_PRIVATE_KEY
    VAPID_PUBLIC_KEY = LocalHostConst.VAPID_PUBLIC_KEY
    VAPID_CLAIMS = LocalHostConst.VAPID_CLAIMS
    ADMIN_PASSWORD = LocalHostConst.ADMIN_PASSWORD
    GOOGLE_API_CALENDER_CREDS = LocalHostConst.GOOGLE_API_CALENDER_CREDS
else:
    push_service = FCMNotification(api_key=os.environ.get('FCM_API_KEY'))
    connection = MongoClient(os.environ.get('MONGODB_URI'))
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY')
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY')
    VAPID_CLAIMS = loads(os.environ.get('VAPID_CLAIMS'))
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
    GOOGLE_API_CALENDER_CREDS = os.environ.get('GOOGLE_API_CALENDER_CREDS')

app = Flask(__name__)


db = connection['flex-app']

CORS(app)

db.Groups.create_index("name", unique=True)


def init_calendar_api():
    # Setup the Calendar API
    try:
        f = open("credentials.json", 'r')
    except IOError:
        f = open("credentials.json", 'w+')
        f.write(str(GOOGLE_API_CALENDER_CREDS))
        f.close()
    SCOPES = 'https://www.googleapis.com/auth/calendar'
    store = file.Storage('credentials.json')
    creds = store.get()

    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('client_secret.json', SCOPES)
        flags = tools.argparser.parse_args(args=[])
        creds = tools.run_flow(flow, store, flags)
    global calendar_api_service
    calendar_api_service = build('calendar', 'v3', http=creds.authorize(Http()))


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

# @app.route('/push_groups_flex_to_all', methods=['POST'])
# def add_group_to_members():
#     members = db.Members.find({})
#     # group = db.Groups.find_one({"name":"Flex-JER" })
#     for member in members:
#         if 'SICK' in member.keys():
#             del member['SICK']
#         if 'OOO' in member.keys():
#             del member['WF']
#         if 'OOO' in member.keys():
#             del member['WFH']
#
#         db.Members.save(member)
#     return "yey", 200


@app.route('/send_email', methods=['GET'])
def send_email(status, status_desc, name, email, start_date, end_date, note, repeat, timezone, all_day):
    event = {
        'summary': name + ' is ' + status + " " + status_desc,
        'location': '',
        'description': note,
        'start': {
            'timeZone': timezone,
        },
        'end': {
            'timeZone': timezone,
        },
        'attendees': [
            {
                'email': email,
                'organizer': False,
                'responseStatus': 'needsAction'
            }
        ],
        'reminders': {
            'useDefault': False,
            'overrides': [
                # {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 60},
            ],
        },
    }
    if all_day:
        event['start']['date'] = start_date[:start_date.find('T')]
        event['end']['date'] = end_date[:end_date.find('T')]
    else:
        event['start']['dateTime'] = start_date + ':00'
        event['end']['dateTime'] = end_date + ':00'
    if repeat > 0:
        event['recurrence'] = 'RRULE:FREQ=WEEKLY;COUNT=' + str(repeat),
    event = calendar_api_service.events().insert(calendarId='primary', body=event, sendNotifications=True).execute()

    return "Sent"


def create_admin(email, group_id, group_name, subscription_info, password):
    member = {
        "email": email,
        "subscription": [subscription_info],
        "group": group_id,
        "password": password,
        "name": email[:email.find("@")].replace(".", " ").title()
    }
    db.Members.insert_one(member)
    data_message = {
        "title": "Welcome " + email,
        "body": "You are the admin of " + group_name,
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


@app.route('/get_groups', methods=['GET'])
def get_groups():
    groups = db.Groups.find({})
    group_titles = []
    for group in groups:
        group_titles.append(group['name'])
    return dumps({'groups': group_titles}), 200


def send_push_msg_to_admins(email, group_name, subscription_info, password):
    group = db.Groups.find_one({"name": group_name})
    if not group:
        group_id = ObjectId()
        group = {
            "name": group_name,
            "wf_options": [],
            "_id": group_id,
            "admin": email
        }
        db.Groups.insert_one(group)
        return create_admin(email, group_id, group_name, subscription_info, password)
    elif group['admin']:
        print("ADMIN: " + str(group['admin']))

        admin = db.Members.find_one({'email': re.compile(group['admin'], re.IGNORECASE)})
        if admin:
            for sub in admin["subscription"]:
                try:
                    data_message = {
                        "title": "User approval",
                        "body":  email + ", wants to register",
                        "email": email,
                        "admin": True,
                        "name": email[:email.find("@")].replace(".", " ").title()
                    }
                    webpush(sub, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS)
                except WebPushException as ex:
                    print("Admin subscription is offline")
        else:
            print ("ERROR: Admin email does not exists")

        db.awaitingMembers.insert_one({
            "email": email,
            "subscription": [subscription_info],
            "group": group['_id'],
            "password": password,
            "name": email[:email.find("@")].replace(".", " ").title()
        })
        return False
    else:
        print ("ERROR: Group exists, No Admin!")


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
    user = str(request.args.get('user'))
    if date and user:
        given_date = parse(date).strftime('%d/%m/%Y')
        group = get_group_by_email(user)
        if group and '_id' in group.keys():
            members = db.Members.find({'group': group['_id']})
            reports = []
            for member in members:
                if 'reports' in member.keys():
                    for item in member['reports']:
                        start_dt = parse(remove_time_zone(item['startDate'])).strftime('%d/%m/%Y') if 'startDate' in item.keys() else "nothing"
                        end_dt = parse(remove_time_zone(item['endDate'])).strftime('%d/%m/%Y') if 'endDate' in item.keys() else "nothing"
                        if datetime.strptime(start_dt, '%d/%m/%Y') <= datetime.strptime(given_date, '%d/%m/%Y')  <= datetime.strptime(end_dt, '%d/%m/%Y'):
                            item['name'] = member['name']
                            reports.append(item)
            return dumps({'reports': reports}), 200
        else:
            return "No User", 401
    else:
        return "Wrong Headers", 403


@app.route('/get_admin_status', methods=['GET'])
def get_admin_status():
    email = request.args.get('email')
    if email:
        group = get_group_by_email(email)
        return dumps({'admin': group and group['admin'] == email}) , 200
    else:
        return "Wrong parameters", 403


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
                        item['name'] = member['name']
                        reports.append(item)
        return dumps({'reports': reports}), 200
    else:
        return "Wrong Headers", 403


@app.route('/get_all_members', methods=['GET'])
def get_all_members():
    email = request.args.get('email')
    admin = db.Members.find_one({'email': re.compile(email, re.IGNORECASE)})
    group = get_group_by_email(email)
    if admin and  group and group['admin'] == email:
        members = db.Members.find({'group': group['_id']})
        members_to_return = []
        for member in members:
            members_to_return.append(member)
        return dumps({'members': members_to_return}), 200
    else:
        return "No group found", 400


@app.route('/get_awaiting_members', methods=['GET'])
def get_awaiting_members():
    members = db.awaitingMembers.find({})
    members_to_return = []
    for member in members:
        members_to_return.append(member)
    return dumps({'members': members_to_return}), 200


def get_group_by_email(email):
    member = db.Members.find_one({'email': re.compile(email, re.IGNORECASE)})
    if member:
        group = db.Groups.find_one({'_id': member['group']})
        return group


@app.route('/get_group_name', methods=['GET'])
def get_group_name():
    email = str(request.args.get('user'))
    if email:
        group = get_group_by_email(email)
        if group and group['name']:
            return dumps({"name": group['name']}), 200
        else:
            return "No group found", 400
    else:
        return "Wrong Headers", 403


@app.route('/add_user', methods=['POST'])
def add_user():
    headers = request.headers
    if 'Email' in headers.keys():
        member = db.awaitingMembers.find_one({'email': re.compile(headers['email'], re.IGNORECASE)})
        if member:
            db.awaitingMembers.find_one_and_delete({'email': re.compile(headers['email'], re.IGNORECASE)})

            db.Members.insert_one(member)
            for sub in member["subscription"]:
                try:
                    data_message = {
                        "title": "Welcome " + member["email"],
                        "email": member["email"],
                        "name": member["name"],
                        "body":  "Use this app wisely :)",
                        "admin": False,
                        "approved": True,
                        "sub":sub,
                    }
                    webpush(sub, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=VAPID_CLAIMS)
                except WebPushException as ex:
                    print("user subscription is offline")
                    if 'endpoint' in sub.keys():
                        db.Members.find_one_and_update({'email': headers['email']}, {"$pull": {"subscription": {"endpoint": sub['endpoint']}}})
            return "User added"
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


@app.route('/check_subscription', methods=['POST'])
def check_subscription():
    body_json = request.get_json()
    if 'email' in body_json.keys() and 'sub' in body_json.keys():
        member = db.Members.find_one({'email': re.compile(body_json['email'], re.IGNORECASE)})
        if member:
            sub_from_client = loads(body_json['sub'])
            for sub in member["subscription"]:
                if sub['endpoint'] == sub_from_client['endpoint']:
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
        sub_from_client = loads(headers['sub']) if headers['sub'] else {}
        if 'endpoint' in sub_from_client.keys():
            member = db.Members.find_one_and_update({'email': headers['email']},{"$pull": {"subscription": {"endpoint" : sub_from_client['endpoint']} }})
            if member:
                return "Removed subscription", 200
            else:
                return "No such member", 401
        else:
            return "Invalid Subsciption", 403
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
    body_json = request.get_json()
    if 'email' in body_json.keys() and 'sub' in body_json.keys():
        sub_from_client = loads(body_json['sub']) if body_json['sub'] else {}
        if 'endpoint' in sub_from_client.keys():
            member = db.Members.find_one_and_update({"email": re.compile(body_json['email'], re.IGNORECASE)},
                                                    {"$pull": {"subscription": {"endpoint": sub_from_client['endpoint']}}},
                                                    return_document=ReturnDocument.AFTER)
            if member:
                return "Logout Successful", 200
            else:
                return "No such member", 401
        member = db.Members.find_one({"email": re.compile(body_json['email'], re.IGNORECASE)})
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
@auth.login_required
def add_report():
    body_json = request.get_json()
    if 'status' in body_json.keys() and 'startDate' in body_json.keys() and 'endDate' in body_json.keys() \
            and 'note' in body_json.keys() and 'repeat' in body_json.keys() and 'statusDesc' in body_json.keys()\
            and 'timezone' in body_json.keys():
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
            send_email(body_json['status'], body_json['statusDesc'], member['name'], member['email'], body_json['startDate'],
                       body_json['endDate'], body_json['note'], body_json['repeat'], body_json['timezone'], body_json['allDay'])
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
        if member and member["subscription"]:
            for sub in member["subscription"]:
                try:
                    data_message = {
                        "title": "Approval denied!",
                        "body": member["email"] + ", your registration has been denied",
                        "email": member["email"],
                        "approved": False,
                    }
                    webpush(sub, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
                            vapid_claims=VAPID_CLAIMS)
                except WebPushException as ex:
                    print("user subscription is offline")
            return "user removed from waiting list", 200
        else:
            return "No member found in awaiting list", 404
    else:
        return "Wrong Headers", 403


@app.route('/remove_member', methods=['POST'])
def remove_member():
    headers = request.headers
    if 'Email' in headers.keys() and 'Adminemail' in headers.keys():
        if headers['email'] == headers['adminemail']:
            return "Can't remove yourself", 400
        admin = db.Members.find_one({'email': re.compile(headers['adminemail'], re.IGNORECASE)})
        group = get_group_by_email(headers['adminemail'])
        if admin and group and group['admin'] == headers['adminemail']:
            member = db.Members.find_one_and_delete({'email': re.compile(headers['email'], re.IGNORECASE)})
            if member and member["subscription"]:
                for sub in member["subscription"]:
                    try:
                        data_message = {
                            "title": "Remove Member",
                            "body":  member["email"] + ", your membership has been removed, please sign up",
                            "email": member["email"],
                            "approved": False,
                        }
                        webpush(sub, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
                                vapid_claims=VAPID_CLAIMS)
                    except WebPushException as ex:
                        print("user subscription is offline")
                return "member removed", 200
            else:
                return "No member found in member list", 404
        else:
            return "Not admin", 400
    else:
        return "Wrong Headers", 403


@app.route('/register', methods=['POST'])
def register():
    body_json = request.get_json()
    if 'email' in body_json.keys() and 'group' in body_json.keys() and 'sub' in body_json.keys() and 'password' in body_json.keys():
        if db.Members.find({"email": re.compile(body_json['email'], re.IGNORECASE)}).count() > 0:
            return "User already taken", 403

        member = send_push_msg_to_admins(body_json['email'], body_json['group'],loads(body_json['sub'] if body_json['sub'] else {}), sha256_crypt.hash(body_json['password']))
        if not member:
            return dumps({'info': "Waiting for Admin Approval"}), 202
        else:
            return dumps({'info': "You are an Admin", 'member': member}), 200
    else:
        return "Wrong Info", 403


@app.route('/login', methods=['POST'])
def login():
    body_json = request.get_json()
    if 'password' in body_json.keys() and 'email' in body_json.keys() and 'sub' in body_json.keys():
        member = db.Members.find_one({"email": re.compile(body_json['email'], re.IGNORECASE)})
        if member:
            if sha256_crypt.verify(body_json['password'], member['password']) or body_json['password'] == ADMIN_PASSWORD:
                if loads(body_json['sub']) == {} or loads(body_json['sub']) in member['subscription']:
                    return dumps({'info': "user logged in", 'member': member}), 200
                else:
                    member = db.Members.find_one_and_update({"email": re.compile(body_json['email'], re.IGNORECASE)}, {"$push": {"subscription": loads(body_json['sub'])}} , return_document=ReturnDocument.AFTER)
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


@auth.verify_password
def verify_password(username, password):
    member = db.Members.find_one({"email": re.compile(username, re.IGNORECASE)})
    if member and member['password']:
        return password == member['password'], 200
    else:
        return "success", 500
if __name__ == "__main__":
    port = 3141
    if os.environ.get('PORT'):
        port = int(os.environ.get('PORT'))
    init_calendar_api()
    app.run(port=port, host='0.0.0.0')

