import os
from pymongo import MongoClient
from pywebpush import webpush, WebPushException
from pyfcm import FCMNotification
import json
import re
import datetime
import sys
from bson.json_util import loads

push_service = None
connection = None
VAPID_PRIVATE_KEY = None
VAPID_PUBLIC_KEY = None
VAPID_CLAIMS = None

if len(sys.argv) > 1 and sys.argv[1] == '--local':
    import LocalHostConst
    push_service = FCMNotification(api_key=LocalHostConst.FCM_API_KEY)
    connection = MongoClient(LocalHostConst.MONGO_URL)
    VAPID_PRIVATE_KEY = LocalHostConst.VAPID_PRIVATE_KEY
    VAPID_PUBLIC_KEY = LocalHostConst.VAPID_PUBLIC_KEY
    VAPID_CLAIMS = LocalHostConst.VAPID_CLAIMS

else:
    push_service = FCMNotification(api_key=os.environ.get('FCM_API_KEY'))
    connection = MongoClient(os.environ.get('MONGODB_URI'))
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY')
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY')
    VAPID_CLAIMS = loads(os.environ.get('VAPID_CLAIMS'))

if datetime.datetime.today().weekday() == 6 or datetime.datetime.today().weekday() == 4:
    print("Wrong weekday: " + str(datetime.datetime.today().weekday()))
else:
    db = connection['flex-app']
    members = db.Members.find({})
    if members and members.count() > 0:
        for doc in members:
            if len(doc["subscription"]) > 0:
                data_message = {
                    "title": "Morning Report",
                    "body": "Morning, What are u up to today?",
                }
                subs_to_keep = []
                for sub in doc["subscription"]:
                    if not sub:
                        continue
                    try:
                        start_search_index = sub['endpoint'].find("//") + 2
                        end_of_url_index = sub['endpoint'][start_search_index:].find("/")
                        VAPID_CLAIMS['aud'] = sub['endpoint'][:(end_of_url_index + start_search_index)]
                        webpush(sub, json.dumps(data_message), vapid_private_key=VAPID_PRIVATE_KEY,
                                vapid_claims=VAPID_CLAIMS, timeout=10)
                        subs_to_keep.append(sub)
                    except WebPushException as ex:
                        print(ex)
                        if ex.response.status_code != 410:
                            subs_to_keep.append(sub)

                    except Exception as ex:
                        print ("unknown exception")
                        print (ex)
                        print (doc['name'])
                doc["subscription"] = subs_to_keep
                db.Members.save(doc)
                subs_to_keep = []