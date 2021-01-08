import json
import os
import re
import time
import uuid
import decimal
from random import random

import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 > 0:
                return float(o)
            else:
                return int(o)
        return super(DecimalEncoder, self).default(o)

class EmptyListError(Exception):
    pass

def get_slots(intent_request):
    return intent_request['currentIntent']['slots']

def confirm_intent(session_attributes, intent_name, slots, message):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'ConfirmIntent',
            'intentName': intent_name,
            'slots': slots,
            'message': message
        }
    }

def close(session_attributes, fulfillment_state, message):
    response = {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': fulfillment_state,
            'message': message
        }
    }

    return response

def delegate(session_attributes, slots):
    return {
        'sessionAttributes': session_attributes,
        'dialogAction': {
            'type': 'Delegate',
            'slots': slots
        }
    }

def submit_reading(intent_request):
    """
    Performs dialog management and fulfillment for meter readings.
    Beyond fulfillment, the implementation of this intent demonstrates the use of the elicitSlot dialog action
    in slot validation and re-prompting.
    """

    slots = intent_request['currentIntent']['slots']
    #postcode = get_slots(intent_request)["Postcode"]
    reading = slots["Reading"]
    utility_type = slots["UtilityType"]
    user_id = slots["UserId"]
    vcode = slots["vcode"]
    customerPhone = slots["Phone"]

    session_attributes = intent_request['sessionAttributes'] if intent_request['sessionAttributes'] is not None else {}

    meter_reading = json.dumps(slots, indent=4, cls=DecimalEncoder)

    session_attributes['MeterReading'] = meter_reading

    dynamodb_IDV = boto3.resource('dynamodb')
    #ID verification section - user_id and vcode
    table_emailsignup = dynamodb_IDV.Table("EmailSignup")
    print("OUTSIDE")
    try:
        print("INSIDE")
        response = table_emailsignup.query(
            ExpressionAttributeValues={
                ':user_id': user_id
            },
            IndexName = 'user_id-index',
            KeyConditionExpression='user_id = :user_id',
        )
        print(response)
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        items = response['Items']
        if not items:
            raise EmptyListError
        else:
            # print("Found user")
            # print(items)
            if str(vcode) == str(items[0]["vcode"]):
                print("YES")
            else:
                print("NO")

    # insert values into the DB.
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ['METER_READING_TABLE_NAME'])

    table.put_item(
        Item = {
            #'postcode': postcode,
            'reading': reading,
            'utility_type': utility_type,
            'timestamp': decimal.Decimal(time.time()),
            'user_id': user_id
        }
    )
    #Jing: Send sms confirmation through SNS
    msg = "Thank you for submitting your {} meter reading. We have updated our records, with a reading of {}. ".format(utility_type, reading)
    snsClient = boto3.client('sns')
    snsClient.publish(
        PhoneNumber = customerPhone,
        Message = msg
    )

    return close(session_attributes,
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': "Thank you for submitting your {} meter reading. "
                  "We have updated our records, "
                  "with a reading of {}. ".format(utility_type, reading)})

def billing_enquiry(intent_request):
    bill = round(random()*100,2)

    return close(intent_request['sessionAttributes'],
                 'Fulfilled',
                 {'contentType': 'PlainText',
                  'content': 'Your current energy bill is £{}.'.format(bill)})

def dispatch(intent_request):
    """
    Called when the user specifies an intent for this bot.
    """
    print(intent_request)
    intent_name = intent_request['currentIntent']['name']

    # Dispatch to your bot's intent handlers
    if intent_name == 'MeterReading':
        return submit_reading(intent_request)
    elif intent_name == 'BillingEnquiry':
        return billing_enquiry(intent_request)

    raise Exception('Intent with name ' + intent_name + ' not supported')

def lambda_handler(event, context):
    """
    Route the incoming request based on intent.
    The JSON body of the request is provided in the event slot.
    """

    return dispatch(event)

