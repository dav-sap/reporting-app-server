from pymongo import MongoClient
from pywebpush import webpush, WebPushException
from pyfcm import FCMNotification
import json
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MONGO_URL = "mongodb://davOwner:1234@ds211588.mlab.com:11588/flex-app"
VAPID_PRIVATE_KEY = open(BASE_DIR + "/private_key.txt", "r+").readline().strip("\n")
VAPID_PUBLIC_KEY = open(BASE_DIR + "/public_key.txt", "r+").read().strip("\n")
VAPID_CLAIMS = {
    "sub": "mailto:sdwhat@europe.com"
}
connection = MongoClient(MONGO_URL)
db = connection['flex-app']
members = db.Members.find({})
if members and members.count() > 0:
    for doc in members:
        try:
            if doc["subscription"]:
                data_message = {
                    "title": "Morning Report",
                    "body": "Morning, What are u up to today?",
                }
                webpush(doc["subscription"], json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims=VAPID_CLAIMS, timeout=10)
        except WebPushException as ex:
            print("subscription is offline")
            db.Members.find_one_and_update({'name': doc['name'], 'email': doc['email']},
                                           {"$set": {"subscription": {}}})