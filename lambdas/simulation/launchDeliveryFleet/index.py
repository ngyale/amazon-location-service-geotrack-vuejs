from urllib import request
from datetime import datetime
import os
import json
import boto3
import logging
import requests
from requests_aws4auth import AWS4Auth

logger = logging.getLogger()
logger.setLevel(logging.INFO)

lambda_client = boto3.client('lambda')
ssm = boto3.client('ssm')
appsync = boto3.client('appsync')

appsync_url = os.getenv('APPSYNC_URL')
project_name = os.getenv('PROJECT_NAME')
project_env = os.getenv('PROJECT_ENC')
pushVehicleLambda = os.getenv('PUSH_VEHICLE_LAMBDA_NAME')

boto3_session = boto3.Session()
credentials = boto3_session.get_credentials()
credentials = credentials.get_frozen_credentials()
items = []

auth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        boto3_session.region_name,
        'appsync',
        session_token=credentials.token,
    )

graphqlQuery="""
    query listDeliveryInfos(
    $filter: ModelDeliveryInfoFilterInput
    $limit: Int
    $nextToken: String
  ) {
    listDeliveryInfos(filter: $filter, limit: $limit, nextToken: $nextToken) {
      items {
        id
        geoStart {
          lat
          lng
        }
        geoEnd {
          lat
          lng
        }
        duration
        distance
        status
        deliveryAgent {
          id
          fullName
          device {
            id
            deliveryAgentId
          }
        }
      }
      nextToken
    }
  }
    """

def getSsmParam(paramKey, isEncrypted):
    try:
        ssmResult = ssm.get_parameter(
            Name=paramKey,
            WithDecryption=isEncrypted
        )

        if (ssmResult["ResponseMetadata"]["HTTPStatusCode"] == 200):
            return ssmResult["Parameter"]["Value"]
        else:
            return ""

    except Exception as e:
        logger.error(str(e))
        return ""

def setProxyResponse(data):
        response = {}
        response["isBase64Encoded"] = False
        if "statusCode" in data:
          response["statusCode"] = data["statusCode"]
        else:
          response["statusCode"] = 200
        if "headers" in data:
            response["headers"] = data["headers"]
        else:
            response["headers"] = {
              'Content-Type': 'application/json', 
              'Access-Control-Allow-Origin': '*' 
            } 
        response["body"] = json.dumps(data["body"])
        return response

def handler(event, context):

    proxy_response = {}

    session = requests.Session()
    session.auth = auth   

    response = session.request(
        url=appsync_url,
        method='POST',
        json={'query': graphqlQuery}
    )    

    if 'data' in response.json():
      items = response.json()['data']['listDeliveryInfos']['items']
      for row in items:
        
        response = lambda_client.invoke(
            FunctionName=str(pushVehicleLambda),
            InvocationType='Event',
            Payload=json.dumps(row)
        )
        logger.info(row['id'] + " StatusCode : " + str(response['ResponseMetadata']['HTTPStatusCode']))

    proxy_response['statusCode']=200
    proxy_response["body"] = { 'msg': 'Processed ' + str(len(items)) + ' vehicles' }

    return setProxyResponse(proxy_response)