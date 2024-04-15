import os, json, requests
from flask import jsonify
from dotenv import load_dotenv
from datetime import datetime
# BT
import braintree
# PP
from requests.auth import HTTPBasicAuth

############## Braintree Configurations ##################
BT_ENVIRONMENT = os.environ.get('BT_ENVIRONMENT')
BT_PUBLIC_KEY = os.environ.get('BT_PUBLIC_KEY_M')
BT_PRIVATE_KEY = os.environ.get('BT_PRIVATE_KEY_M')
BT_MERCHANT_ID = os.environ.get('BT_MERCHANT_ID_M')
BT_VERSION = '2024-01-01'

##########################################################

############## PayPal Configurations ##################
PP_SANDBOX_URL = 'https://api-m.sandbox.paypal.com'
PP_CLIENT_ID = os.environ.get('PPAC_CLIENT_ID')
PP_SECRET = os.environ.get('PPAC_SECRET')
PPCUST = os.environ.get('PPCUST1')
INVOICE = str(round(datetime.now().timestamp()))
BILLING_ADDRESS = os.environ.get('US_BILL_ADD')
cache_file = '/var/tmp/outh.json'

# Payment source for PayPal
PSOURCE_PP = {
    "paypal": {
        # attirbutes is not needed for return customers
        "attributes": {
            "customer": {
                "id": PPCUST 
                #"email": ""
            },
            "vault": {
                "store_in_vault": "ON_SUCCESS",
                "usage_pattern": "IMMEDIATE",   # buyer-present, non-recurring
                "usage_type": "MERCHANT",  # For merchant 
                "customer_type": "CONSUMER",  # For merchant 
                "permit_multiple_payment_tokens": True  # For merchant 
            }
        },
        "experience_context": {
            "brand_name": "VAULT_PP INC",
            "locale": "en-US",
            "return_url": "http://127.0.0.1:4567/pp/order/api", # only for order v2
            "cancel_url": "http://127.0.0.1:4567/pp/order/api", # only for order v2
            "user_action": "PAY_NOW",   # "CONTINUE"
            "landing_page": "LOGIN",    # "GUEST_CHECKOUT"
            "shipping_preference": "NO_SHIPPING",   # "SET_PROVIDED_ADDRESS", "GET_FROM_FILE"
            "payment_method_preference": "IMMEDIATE_PAYMENT_REQUIRED" # Immediate payment method
        }
    }
}

# Payment source for Card
PSOURCE_CC = {
    "card": {
        "attributes": {
            "customer": {
                "id": PPCUST,
                "email_address": 'test2@test2.com'  
            },
            "vault": { # vault
                "store_in_vault": "ON_SUCCESS"
            }
            #"verification": { # 3DS
            #    "method": "SCA_ALWAYS"
           #}
        },
    },   
}

# Vaulted paypal payment order v2
VAULTED_PP = {
    "paypal": {
        "vault_id": ""
    },
} 

# Vaulted credit card payment order v2
VAULTED_CC = {
    "card": {
        "vault_id": ""
    },
} 

# PayPal checkout body
SINGLE_BODY = {
    "intent": "CAPTURE",
    "purchase_units": [{
        #"reference_id": "Input merchant reference number",
        "description": "Transaction description",
        "custom_id": "Merchant custom id if any",
        #"invoice_id": str(datetime.now()),
        "amount": {
            "currency_code": "",
            "value": "",
            #"breakdown": DIGITAL_BREAKDOWN
        },
        "payer": {
            "email_address": "test1@test.com",
            "address": {
                "country_code": "US"
            }
        }
        #"items": ITEMS
        #"supplementary_data": SUPPLEMENTARY_DATA
    }],
    "payment_source": PSOURCE_PP
}

##########################################################

##########################################################
############ Braintree Server SDK APIs ###################
# To initiate Braintree SDK
gateway = braintree.BraintreeGateway(
    braintree.Configuration(
        environment=BT_ENVIRONMENT,
        merchant_id=BT_MERCHANT_ID,
        public_key=BT_PUBLIC_KEY,
        private_key=BT_PRIVATE_KEY
    )
)

# API to generate client token to initialize client SDKs
def generate_client_token(id):
    return gateway.client_token.generate(id)

# API to transact.sale deduct money
def transact(options):
    return gateway.transaction.sale(options)

# API to search for transaction
def find_transaction(id):
    return gateway.transaction.find(id)

# API to search for customer
def find_customer(id):
    return gateway.customer.find(id)

##########################################################

##########################################################
############ Braintree GraphQL APIs ###################
# To initiate graphQL API
def gpl_init():
    endpoint = f"https://payments.sandbox.braintree-api.com/graphql"
    username = BT_PUBLIC_KEY
    password = BT_PRIVATE_KEY
    header = {
        "Braintree-Version": BT_VERSION,
        "Content_Type": 'application/json'
    }
    return {"header" : header, "endpoint" : endpoint, "username" : username, "pwd" : password}

# To create client token
def gql_create_client_token(custID, mecID): 
    query = """mutation ClientToken($input: CreateClientTokenInput!) {
        createClientToken(input: $input) {
            clientToken
        }
    }"""
    variables = {
        "input": {
            #"clientMutationId": 'testclientmutationId123',
            ## For non-vault, don't pass anything to input
            "clientToken": {
                "customerId": custID,
                "merchantAccountId": mecID #optional
            }
        }
    }

    result = requests.post(gpl_init()["endpoint"], json={"query": query, "variables" : variables}, headers=gpl_init()["header"], auth=(gpl_init()["username"], gpl_init()["pwd"]))
    if result.status_code == 200:
        return result.json()
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(result.status_code, query))

# Charge any payment method + device_data
def gql_transact_sale(nonce, maid, amt, device_data): 
    
    query = """mutation TransactionSale($input: ChargePaymentMethodInput!) {
        chargePaymentMethod(input: $input) {
            transaction {
                id
                legacyId
                orderId
                merchantAccountId
                status
                amount {
                    currencyCode
                    value
                }
                paymentMethodSnapshot {
                    __typename
                    ... on PayPalTransactionDetails {
                        captureId
                    }
                }
            }
        }
    }"""
    variables = {
        "input": {
            "paymentMethodId": nonce,
            "transaction": {
                "orderId": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "merchantAccountId": maid,
                "amount": amt,
                "riskData": {
                    "deviceData": device_data
                }
            }
        }
    }

    result = requests.post(gpl_init()["endpoint"], json={"query": query, "variables" : variables}, headers=gpl_init()["header"], auth=(gpl_init()["username"], gpl_init()["pwd"]))
    if result.status_code == 200:
        return result.json()
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(result.status_code, query))

# Charge PayPal payment method - for pwpp
def gql_paypal_sale(nonce, curr, amt, device_data): 
    
    query = """mutation PayPalSale($input: ChargePayPalAccountInput!) {
        chargePayPalAccount(input: $input) {
            clientMutationId
            transaction {
                id
                legacyId
                orderId
                createdAt
                status
            }
        }
    }"""
    variables = {
        "input": {
            "clientMutationId": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "paymentMethodId": nonce,
            "options": {
                "description": "PUBG Diamond 30 - developer name",
                "riskContext":{
                    "fields": [{
                        "name": "sender_account_id",
                        "value": "Buyer's Platform Account Number"
                    },
                    {
                        "name": "sender_first_name",
                        "value": "Mary"
                    },
                    {
                        "name": "sender_last_name",
                        "value": "Lee"
                    },
                    {
                        "name": "sender_country_code",
                        "value": "SG"
                    }]
                }
            },
            "transaction": {
                "merchantAccountId": curr,
                "amount": amt
            }    
        }
    }

    result = requests.post(gpl_init()["endpoint"], json={"query": query, "variables" : variables}, headers=gpl_init()["header"], auth=(gpl_init()["username"], gpl_init()["pwd"]))
    if result.status_code == 200:
        return result.json()
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(result.status_code, query))

def gql_search_transact(maid,txnId):
    # riskData only for credit card, paypal will have to check with PayPal tool & Risk
    query = """query SearchTransaction($input: TransactionSearchInput!) {
        search {
            transactions(input: $input) {
                edges {
                    node {
                        id
                        legacyId
                        orderId
                        status
                        amount {
                            currencyCode
                            value
                        }
                        createdAt
                        paymentMethodSnapshot {
                            __typename
                            ... on CreditCardDetails {
                                brandCode
                                bin
                                expirationMonth
                                expirationYear
                                origin { type }
                                threeDSecure { authentication { liabilityShifted } }
                            }
                            __typename
                            ... on PayPalTransactionDetails {
                                captureId
                                payerStatus
                                sellerProtectionStatus
                                transactionFee {
                                    value
                                    currencyCode
                                }
                                description
                            }
                        }
                        riskData { 
                            decision
                            decisionReasons
                            deviceDataCaptured
                        }
                        statusHistory {
                            status
                            timestamp
                        }
                        lineItems {
                            name
                            description
                        }
                    }
                }
            }
        }
    }"""
    variables = {
        "input": {
            "merchantAccountId": {
                "is": maid
            },
            "id": {
                "is": txnId
            }
        }
    }

    result = requests.post(gpl_init()["endpoint"], json={"query": query, "variables" : variables}, headers=gpl_init()["header"], auth=(gpl_init()["username"], gpl_init()["pwd"]))
    if result.status_code == 200:
        return result.json()
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(result.status_code, query))


# For redirect STC calls
def gql_stc():
    query = """mutation PayPalSTC($input: CreateTransactionRiskContextInput!) {
        createTransactionRiskContext(input: $input) {
            clientMetadataId
        }
    }"""
    
    variables = {
        "input": {
            "riskContext":{
                "fields":[{
                    "name": "sender_account_id",
                    "value": "xyz123"
                },
                {
                    "name": "txn_count_total",
                    "value": "15987"
                }]
            }		 		
        }
    }

    result = requests.post(gpl_init()["endpoint"], json={"query": query, "variables" : variables}, headers=gpl_init()["header"], auth=(gpl_init()["username"], gpl_init()["pwd"]))
    if result.status_code == 200:
        return result.json()
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(result.status_code, query))

##########################################################

##########################################################
############# PayPal Server Order APIs ###################
# Request Oauth Token for PayPal APIs
def create_pp_oauth_token():
    endpoint = PP_SANDBOX_URL + "/v1/oauth2/token"
    header = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    body = {
        "grant_type": 'client_credentials',
        "response_type": 'id_token',  # For SPB vault v3
        "target_customer_id": PPCUST  # For SPB vault v3 
    }
    auth = HTTPBasicAuth(PP_CLIENT_ID, PP_SECRET)
    response = requests.post(endpoint, data=body, headers=header, auth=auth)
    result = response.json()
    result['expiration_time'] = int(round(datetime.now().timestamp())) + response.json()['expires_in']

    # Write the response to a file for repeat usage
    with open(cache_file, "w") as outfile:
        json.dump(result, outfile)   
    #return result['access_token']
    return result

# Reuse Token from cache file
def getCachedOauthToken():
    current = int(round(datetime.now().timestamp()))
    if os.path.exists(cache_file):
        # Reading cache
        with open(cache_file, "r") as infile:
            filedata = json.load(infile)
            result = filedata
        if current > filedata['expiration_time']:
            # Token expired, get new
            result = create_pp_oauth_token()
    else:
        # No cached value, get and cache
        result = create_pp_oauth_token()   
    return result

# Get Oauth Token Response directly without reuse
def getOauthToken():
    accessTokenResponse = create_pp_oauth_token() # for direct token retrieval
    return accessTokenResponse

# Generate Client Token for ACDC
def createPPClientToken(cust):
    accessToken = getOauthToken()['access_token']
    url = PP_SANDBOX_URL + "/v1/identity/generate-token"
    header = {
        "Authorization": 'Bearer ' +  accessToken,
        "Accept-Language": "en_US",
        "Content_Type": 'application/json'
    }
    body = { "customer_id": cust } 
    #body = {}
    response = requests.post(url, json=body, headers=header)
    if(response):
        return response.json()["client_token"]
    else: return ""

# SPB Create Order API
def createOrder(data):
    accessToken = getOauthToken()['access_token']
    url = PP_SANDBOX_URL + "/v2/checkout/orders"
    header = {
        "Content_Type": 'application/json',
        "Authorization": 'Bearer ' +  accessToken,
        "PayPal-Request-Id": str(round(datetime.now().timestamp()))
    }
    print("SPB DATA: ", data)
    SINGLE_BODY['purchase_units'][0]['amount']['currency_code'] = data['currency']
    SINGLE_BODY['purchase_units'][0]['amount']['value'] = data['amount']
    
    # 1. PayPal SPB vault not checked or already vaulted
    if(data['source'] == 'paypal' and data['vault_pp'] == False):
        psource = PSOURCE_PP
        if('vault' in psource['paypal']['attributes']):
            psource['paypal']['attributes'].pop('vault')
            SINGLE_BODY['payment_source'] = psource
            print('vault pp: ', SINGLE_BODY)
    # 2. Vault PayPal SPB
    if(data['source'] == 'paypal' and data['vault_pp'] == True):
        SINGLE_BODY['payment_source'] = PSOURCE_PP
    
    # 3. Hosted Field Card, vault not checked
    if(data['source'] == 'card' and data['token'] == 'card'):
        ccsource = PSOURCE_CC
        if(data['vault_cc'] == False and ('vault' in ccsource['card']['attributes'])):
            ccsource['card']['attributes'].pop('vault')
            SINGLE_BODY['payment_source'] = ccsource
        # 4. Hosted Field Card, vault is checked
        SINGLE_BODY['payment_source'] = PSOURCE_CC

    # Vaulted hosted field use ORIGINAL SINGLE_BODY
    print("createOrder BODY: " , SINGLE_BODY)
    response = requests.post(url, json=SINGLE_BODY, headers=header)
    print("createOrderResponse: ", response.json())
    return response.json()

# Order v2 Create Order API
def createOrderAPI(data):
    accessToken = getOauthToken()['access_token']
    url = PP_SANDBOX_URL + "/v2/checkout/orders"
    header = {
        "Content_Type": 'application/json',
        "Authorization": 'Bearer ' +  accessToken,
        "PayPal-Request-Id": str(round(datetime.now().timestamp()))
    }

    print("API data: ", data)
    SINGLE_BODY['purchase_units'][0]['amount']['currency_code'] = data['currency']
    SINGLE_BODY['purchase_units'][0]['amount']['value'] = data['amount']

    # 1. PayPal order v2 api vault not checked or already vaulted
    if(data['source'] == 'paypal' and data['vault'] == 'no'):
        print('paypal checkout with no vault')
        psource = PSOURCE_PP
        if('vault' in psource['paypal']['attributes']):
            psource['paypal']['attributes'].pop('vault')
            SINGLE_BODY['payment_source'] = psource
    # 2. To Vault PayPal wallet order v2 api
    if(data['source'] == 'paypal' and data['vault'] == 'yes'):
        print('paypal checkout with vault')
        SINGLE_BODY['payment_source'] = PSOURCE_PP
    
    # 3. Vault card via order v2
    if(data['source'] == 'card'):
        ccsource = PSOURCE_CC
        ccsource['card']['number'] = data['number']
        ccsource['card']['expiry'] = data['expiry']
        ccsource['card']['name'] = data['name']
        billing_address = { 
            "address_line_1": data['billing_address']['address_line_1'],
            "address_line_2": data['billing_address']['address_line_2'],
            "admin_area_2": data['billing_address']['admin_area_2'],
            "admin_area_1": data['billing_address']['admin_area_1'],
            "postal_code": data['billing_address']['postal_code'],
            "country_code": data['billing_address']['country_code']
        }
        ccsource['card']['billing_address'] = billing_address
        if((data['vault'] == 'no') and ('vault' in ccsource['card']['attributes'])):
            print('credit card checkout with no vault')
            ccsource['card']['attributes'].pop('vault')
            SINGLE_BODY['payment_source'] = ccsource
        if(data['vault'] == 'yes'):
            SINGLE_BODY['payment_source'] = ccsource

    print("API createOrder BODY: " , SINGLE_BODY)
    response = requests.post(url, json=SINGLE_BODY, headers=header)
    return response.json()

# Order v2 Create Order API with vaulted token
def vaultedCreateOrderAPI(data):
    accessToken = getOauthToken()['access_token']
    url = PP_SANDBOX_URL + "/v2/checkout/orders"
    header = {
        "Content_Type": 'application/json',
        "Authorization": 'Bearer ' +  accessToken,
        "PayPal-Request-Id": str(round(datetime.now().timestamp()))
    }

    print("API data: ", data)
    SINGLE_BODY['purchase_units'][0]['amount']['currency_code'] = data['currency']
    SINGLE_BODY['purchase_units'][0]['amount']['value'] = data['amount']

    # 1. Vaulted PayPal wallet order v2 api
    if(data['source'] == 'paypal' and data['token']):
        print('paypal checkout with vaulted token')
        ppsource = VAULTED_PP
        ppsource['paypal']['vault_id'] = data['token']
        SINGLE_BODY['payment_source'] = ppsource
    
    # 2. Vaulted card via order v2
    if(data['source'] == 'card' and data['token']):
        print('cc checkout with vaulted token')
        ccsource = VAULTED_CC
        ccsource['card']['vault_id'] = data['token']
        SINGLE_BODY['payment_source'] = ccsource

    print("API createOrder BODY: " , SINGLE_BODY)
    response = requests.post(url, json=SINGLE_BODY, headers=header)
    return response.json()

# Capture Order API
def captureOrder(orderid):
    accessToken = getOauthToken()['access_token']
    url = PP_SANDBOX_URL + "/v2/checkout/orders/" + orderid + "/capture"
    header = {
        "Content_Type": 'application/json',
        "Authorization": 'Bearer ' +  accessToken,
        "PayPal-Request-Id": str(round(datetime.now().timestamp()))
    }
    response = requests.post(url, headers=header)
    #print("capture: ", response.json())
    return response.json()

# PayPal delete, refund & update functions
def pp_update(data):
    accessToken = getOauthToken()['access_token']
    header = { 
        "Content_Type": 'application/json',
        "Authorization": 'Bearer ' +  accessToken,
        "PayPal-Request-Id": str(round(datetime.now().timestamp()))
    }
    url = PP_SANDBOX_URL + "/v2/payments/captures/" + data['txn_id'] + "/refund"
    body = {
        "amount": {
            "value": "5.00",
            "currency_code": "USD"
        },
        'custom_id': data['invoice_id'],
        'note_to_payer': data['note_to_payer']
    }
    try:
        response = requests.post(url, json=body, headers=header)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        print('errors:', e)
        return e
    
def pp_delete(data):
    accessToken = getOauthToken()['access_token']
    header = { "Authorization": 'Bearer ' +  accessToken }
    url = PP_SANDBOX_URL + "/v3/vault/payment-tokens/" + data['txn_id']
    try:
        response = requests.delete(url, headers=header)
        #response.raise_for_status()
        print(response.status_code)
        return response
    except requests.exceptions.HTTPError as e:
        print('errors:', e)
        return e
    
############# PayPal Server Get APIs ###################
# Get Customer's Vault Token API
def getCustVault(custid):
    accessToken = getOauthToken()['access_token']
    url = PP_SANDBOX_URL + "/v3/vault/payment-tokens?customer_id=" + custid
    header = {
        "Content_Type": 'application/json',
        "Authorization": 'Bearer ' +  accessToken,
    }
    try:
        response = requests.get(url, headers=header)
        #print(response.json())
        if(response.status_code == 200):
            return response.json()
        else: return "400"
    except requests.exceptions.RequestException as e:  # This is the correct syntax
        raise SystemExit(e)

# All PayPal search functions
def pp_search(id,id_type):
    accessToken = getOauthToken()['access_token']
    if(id_type == 'order'):
        url = PP_SANDBOX_URL + "/v2/checkout/orders/" + id
    if(id_type == 'payment'):
        url = PP_SANDBOX_URL + "/v2/payments/captures/" + id
    if(id_type == 'customer'):
        url = PP_SANDBOX_URL + "/v3/vault/payment-tokens?customer_id=" + id
    if(id_type == 'token'):
        url = PP_SANDBOX_URL + "/v3/vault/payment-tokens/" + id
    if(id_type == 'ba'):
        url = PP_SANDBOX_URL + "/v1/payments/billing-agreements/" + id
    if(id_type == 'refund'):
        url = PP_SANDBOX_URL + "/v2/payments/refunds/" + id
    
    header = { "Authorization": 'Bearer ' +  accessToken }
    try:
        response = requests.get(url, headers=header)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        return e
##########################################################