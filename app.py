################# Import Classes and Functions #################
import os, requests
from datetime import datetime
from flask import Flask, redirect, url_for, render_template, request, flash, jsonify
#from os.path import join, dirname
from dotenv import load_dotenv

# Import Braintree defined classes in __init__
import braintree
from gateway import generate_client_token, transact, find_transaction, find_customer
from gateway import gql_create_client_token, gql_transact_sale, gql_paypal_sale, gql_stc, gql_search_transact, gpl_init

# Import PayPal defined classes in __init__
from gateway import createPPClientToken, getOauthToken
from gateway import createOrder, captureOrder, createOrderAPI, vaultedCreateOrderAPI
from gateway import getCustVault, pp_search, pp_update, pp_delete
################## Initializes Environment #####################
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('APP_SECRET_KEY')
PORT = int(os.environ.get('PORT', 4567))

## Home page route
@app.route('/', methods=['GET'])
def index():
    return render_template('main.html')

################## Braintree Setup Variables ######################
#app.secret_key = os.environ.get('APP_SECRET_KEY')
#username = os.environ.get('BT_PUBLIC_KEY')
#password = os.environ.get('BT_PRIVATE_KEY')
pwpp_client_id = os.environ.get('BT_PWPP_M')       # need to tally with BT control panel setup
bt_cust_id = os.environ.get('BTCUST4')           # setup existing customer

TRANSACTION_SUCCESS_STATUSES = [
    braintree.Transaction.Status.Authorized,
    braintree.Transaction.Status.Authorizing,
    braintree.Transaction.Status.Settled,
    braintree.Transaction.Status.SettlementConfirmed,
    braintree.Transaction.Status.SettlementPending,
    braintree.Transaction.Status.Settling,
    braintree.Transaction.Status.SubmittedForSettlement,
    'AUTHORIZED', 'AUTHORIZING', 'SETTLED', 'SETTLEMENT_CONFIRMED', 'SETTLEMENT_PENDING', 'SETTLING', 'SUBMITTED_FOR_SETTLEMENT'
]

################### PayPal Setup Variables #######################
PP_CLIENT_ID = os.environ.get('PPAC_CLIENT_ID')
PPCUST = os.environ.get('PPCUST1')
COUNTRY = os.environ.get('COUNTRY')
CURRENCY = os.environ.get('CURRENCY')

PP_TXN_STATUS = ['COMPLETED','PENDING']
##################################################################
################## Setup Braintree SDK Routes ####################
##################################################################
## BT dropin route
@app.route('/bt/dropin', methods=['GET'])
def bt_dropin_route():
    client_token = generate_client_token({
        "merchant_account_id": "TEST_" + CURRENCY,
        "customer_id": bt_cust_id
    })
    return render_template('gateways/braintree/dropin.html', client_token=client_token)

## BT hostedfield route
@app.route('/bt/hostedfield', methods=['GET'])
def bt_hostedfield_route():
    client_token = generate_client_token({
        "merchant_account_id": "TEST_" + CURRENCY,
        "customer_id": bt_cust_id
    })
    return render_template('gateways/braintree/hostedfield.html', client_token=client_token, currency=CURRENCY)

## BT pwpp route
@app.route('/bt/pwpp', methods=['GET'])
def bt_pwpp_route():
    client_id = pwpp_client_id
    pp_vaulted = 'N'
    cust = bt_cust_id  #49056444653, 52075236181
    try: 
        customer = find_customer(cust)
        for obj in customer.payment_methods:
            if obj == 'PayPalAccount':
                if(obj.billing_agreement_id):
                    pp_vaulted = 'Y'
                    print(obj.billing_agreement_id)
    except braintree.exceptions.not_found_error.NotFoundError as e:
        cust = ""
        print("Customer not found: ", e)

    client_token = generate_client_token({
        "merchant_account_id": "TEST_"+CURRENCY,  # for multi-account
        "customer_id": cust       # only for dropin
    })
    return render_template('gateways/braintree/pwpp.html', client_token=client_token, client_id=client_id, currency=CURRENCY, country=COUNTRY, pp_vaulted=pp_vaulted)

## Braintree transaction.sale server-side
@app.route('/server/sdk/checkout', methods=['POST'])
def sdk_transaction_sale():
    #print(request.form)
    result = transact({
        'payment_method_nonce': request.form['payment_method_nonce'],
        'amount': request.form['amount'],
        ## optional data pass in: merchant invoice/order number for reference, paypal inv field
        'order_id' : "Unique invoice - " + datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        ## optional for multi-currency
        'merchant_account_id': 'TEST_'+CURRENCY,
        ## optional for existing customer for vault
        'customer_id': bt_cust_id,
         # only if device_data is collected: paypal vault or fpa
        "device_data": request.form["device_data"],
        'options': {
            ## this is for captue / auth
            "submit_for_settlement": True,
            ## Vault: This will create a new customer with save payment method, vault with purchase if customerid is not stated
            'store_in_vault_on_success': True,
            #'paypal': {
                ## Merchant needed information
            #    "custom_field" : "PayPal custom field, appear in paypal report",
                ## Compliance requirement: this will appear in admin tool
            #    "description" : "PUBG - Cash Topup",
                ## STC data requirements for gaming
            #    "supplementary_data": {
            #        "sender_account_id": "Buyer's Huawei Account Number",
            #        "sender_first_name": "Mary",   # Buyer's first_name
            #        "sender_last_name": "Lee",     # Buyer's last_name 
            #        "sender_email": "marylee@hotmail.com", # Email registered with Huawei
            #        "sender_phone": "(65) 98765432", # Phone registered with Huawei
            #        "sender_country_code": "SG", # country code registerde with Huawei
            #        "sender_create_date": "2012-12-09T19:14:55.277-0:00" # date of creation of huawei account
            #    }
            #},
        }
    })

    print("result: ", print_paypal_account(result.transaction))

    if result.is_success or result.transaction:
        return redirect(url_for('bt_show_txn', type="txn", transaction_id=result.transaction.id))
    else:
        for x in result.errors.deep_errors: flash('Error: %s: %s' % (x.code, x.message))
        return redirect(url_for('bt_show_txn'))

def print_paypal_account(paypal_account):
    attributes = {
        key: value for key, value in paypal_account.__dict__.items() if value is not None
    }
    return f"<PayPalAccount {attributes} at {id(paypal_account)}>"

#### Search & Manage functions in Braintree ####
## Route to render Braintee search and manage
@app.route('/bt/search_manage', methods=['GET'])
def bt_search_manage_render():
    return render_template('gateways/braintree/search_manage.html')

## Route to get order
@app.route('/bt/search_manage', methods=['POST'])
def bt_get_txn():    
    if(request.form.get('pptxn')!=""):
        id = request.form.get('pptxn')
        id_type = 'payment'
    if(request.form.get('ppcust')!=""):
        id = request.form.get('ppcust')
        id_type = 'customer'
    if(request.form.get('pptoken')!=""):
        id = request.form.get('pptoken')
        id_type = 'token'
    if(request.form.get('ppba')!=""):
        id = request.form.get('ppba')
        id_type = 'ba'
    return redirect(url_for('bt_show_txn', id=id))

## Show Braintree transaction details if found
#@app.route('/bt/find/<transaction_id>', methods=['GET'])
@app.route('/bt/show/<type>/<transaction_id>', methods=['GET'])
def bt_show_txn(type, transaction_id):
    transaction = find_transaction(transaction_id)
    gql_txn = gql_search_transact(type,transaction_id)
    result = {}
    if transaction.status in TRANSACTION_SUCCESS_STATUSES:
        result = {
            'header': 'Sweet Success!',
            'icon': 'success',
            'message': 'Your test transaction has been successfully processed. See the Braintree API response and try again.'
        }
    else:
        result = {
            'header': 'Transaction Failed',
            'icon': 'fail',
            'message': 'Your test transaction has a status of ' + transaction.status + '. See the Braintree API response and try again.'
        }

    return render_template('gateways/bt_show.html', gql_txn=gql_txn, transaction=transaction, result=result)

##################################################################
#################### Setup Braintree GraphQL Routes #####################
##################################################################
## BT GraphQL Generate client_token route
@app.route('/btgql/pwpp', methods=['GET'])
def btgql_pwpp_route():
    client_id = pwpp_client_id
    pp_vaulted = 'N'
    cust = bt_cust_id  #49056444653, 52075236181
    client_token = gql_create_client_token(cust, "TEST_"+CURRENCY)["data"]["createClientToken"]['clientToken']
    clientMetadataId = gql_stc()['data']['createTransactionRiskContext']['clientMetadataId']
    print("stc data: ", gql_stc())
    return render_template('gateways/braintree/pwpp.html', client_token=client_token, client_id=client_id, currency=CURRENCY, country=COUNTRY, pp_vaulted=pp_vaulted,riskCorrelationId=clientMetadataId)

## Braintree GraphQL transaction.sale
@app.route('/server/gql/checkout', methods=['POST'])
def gql_transaction_sale():
    nonce = request.form['payment_method_nonce']
    maid = "TEST_"+CURRENCY
    amount = request.form['amount']
    selection = request.form['vaultselect']

    # RDA data
    device_data = request.form['device_data']
    print("device data: ", device_data)

    # Passed parameter to GQL charge payment
    if(selection == 'o3'):    
        result = gql_transact_sale(nonce, maid, amount, device_data)
    else: 
        result = gql_paypal_sale(nonce, maid, amount, device_data)
    print(result)

    if result['data']:
        if(selection == 'o3'):
            txnId = result['data']['chargePaymentMethod']['transaction']['id']
        else:
            txnId = result['data']['chargePayPalAccount']['transaction']['id']
        return redirect(url_for('bt_show_txn', type="txn", transaction_id=txnId))
    else:
        flash(result)
        return redirect(url_for('/'))

##################################################################
###### Setup Braintree GraphQL Routes for mobile apps ############
##################################################################
## Braintree GraphQL transaction.sale
@app.route('/gql/client_token', methods=['POST'])
def gql_clienttoken():
    custId = request.get_json()['customerId']
    mecId = request.get_json()['merchantAccountId']

    result = gql_create_client_token(custId, mecId)
    client_token = result["data"]["createClientToken"]['clientToken']
    print(client_token)
    return jsonify({"value":client_token})

## Braintree GraphQL transaction.sale
@app.route('/gql/stc', methods=['POST'])
def gql_stc():
    result = gql_stc()
    clientMetaDataID = result["data"]["createTransactionRiskContext"]['clientMetadataId']
    print(clientMetaDataID)
    return jsonify({"value":clientMetaDataID})

## Braintree GraphQL transaction.sale
@app.route('/gql/sale', methods=['POST'])
def gql_sale():
    #print(request.get_json())
    nonce = request.get_json()['paymentMethodNonce']
    mecId = request.get_json()['merchantAccountId']
    amt = request.get_json()['amount']
    device_data = "12345678910123"
    result = gql_transact_sale(nonce, mecId, amt, device_data)
    orderId = result['data']['chargePaymentMethod']['transaction']['id']
    status = result['data']['chargePaymentMethod']['transaction']['status']
    message = "created. Payment has been completed successfully, " + "the orderid is: " + orderId + " with a status of " + status
    print(result)
    return jsonify({"message":message})

##################################################################
#################### Setup PayPal SDK Routes #####################
##################################################################
## PayPal JSSDK route
@app.route('/pp/spb', methods=['GET'])
def spb_route():
    id_token = getOauthToken()['id_token']      # SPB vault v3
    client_token = createPPClientToken(PPCUST)  # ACDC vault v3
    cust_vault = getCustVault(PPCUST)
    vaultppalr = 'N'

    ## note: if paypal is vaulted with Balance or Bank, review page will still show
    if(cust_vault != "400"): 
        if('payment_tokens' in cust_vault):
            for key in cust_vault['payment_tokens']:
                if('paypal' in key['payment_source']):
                    print("yes vaulted")
                    vaultppalr = 'Y' 
        
    return render_template('gateways/paypal/spb_cardfield.html', id_token=id_token, client_token=client_token, client_id=PP_CLIENT_ID, 
                           vaultppalr=vaultppalr, curr=CURRENCY, country=COUNTRY)

## Route to create order - depend on the payload can activate single order without capture call
@app.route('/pp/spb/order/create', methods=['POST'])
def spb_create_order():   
    data = request.get_json(force=True) 
    result = createOrder(data) 
    return result

## Route to capture order
@app.route('/pp/spb/order/<id>/capture', methods=['POST'])
def spb_capture_order(id):    
    transaction = captureOrder(id)
    print("capture data: ", transaction)
    return transaction

## Route to get order
@app.route('/pp/spb/order/<id>', methods=['GET'])
def spb_get_order(id):    
    transaction = pp_search(id,'order')
    return transaction

## PayPal Order V2 route
@app.route('/pp/order/api', methods=['GET'])
def pp_order_route():
    result = getCustVault(PPCUST)
    if(result != "400"): 
        if('payment_tokens' not in result): result = 400
    return render_template('gateways/paypal/orderv2.html', methods=result, client_id=PP_CLIENT_ID, 
                           curr=CURRENCY, country=COUNTRY)

## PayPal Order V2 create order API route
@app.route('/pp/order/api/create', methods=['POST'])
def pp_order_create():
    data = request.get_json(force=True) 
    if ('token' in data): 
        result = vaultedCreateOrderAPI(data) 
    else: result = createOrderAPI(data) 
    print("single order for pp" , result)
    return result

## PayPal Order V2 create order API route
@app.route('/cc/order/api/create', methods=['POST'])
def cc_order_create():
    data = request.get_json(force=True) 
    result = createOrderAPI(data) 
    id = result['purchase_units'][0]['payments']['captures'][0]['id']
    print("single order for cc" , id)
    return result

#### Search & Manage functions in PayPal ####
## Route to render PayPal search and manage
@app.route('/pp/search_manage', methods=['GET'])
def pp_search_manage_render():
    return render_template('gateways/paypal/search_manage.html')

## Route to refund/update order
@app.route('/pp/spb/refund', methods=['POST'])
def pp_refund_txn(): 
    data = request.get_json(force=True)
    response = pp_update(data)
    return redirect(url_for('pp_show_txn', id=response['id']))

## Route to delete token
@app.route('/pp/spb/delete', methods=['DELETE'])
def pp_delete_token(): 
    data = request.get_json(force=True)
    response = pp_delete(data)
    if(response.status_code == '204'):
        print('delete response successful!')
        return redirect(url_for('index'))
    else: return "Failed!"

## Route to get order
@app.route('/pp/spb/search_manage', methods=['POST'])
def pp_get_txn():    
    if(request.form.get('pporder')!=""):
        id = request.form.get('pporder')
        id_type = 'order'
    if(request.form.get('pptxn')!=""):
        id = request.form.get('pptxn')
        id_type = 'payment'
    if(request.form.get('ppcust')!=""):
        id = request.form.get('ppcust')
        id_type = 'customer'
    if(request.form.get('pptoken')!=""):
        id = request.form.get('pptoken')
        id_type = 'token'
    if(request.form.get('ppba')!=""):
        id = request.form.get('ppba')
        id_type = 'ba'
    return redirect(url_for('pp_show_txn', id=id, id_type=id_type))

## Show PayPal transaction details if found
@app.route('/pp/find/<id_type>/<id>', methods=['GET'])
def pp_show_txn(id,id_type):
    # Search type
    if(id_type == 'order'): 
        details = pp_search(id,id_type)
    if(id_type == 'payment'): 
        details = pp_search(id,id_type)
    if(id_type == 'customer'): 
        details = pp_search(id,id_type)
    if(id_type == 'token'): 
        details = pp_search(id,id_type)
    if(id_type == 'ba'): 
        details = pp_search(id,id_type)
    if(id_type == 'refund'): 
        details = pp_search(id,id_type)
    if(id_type == 'delete'): 
        details = pp_search(id,id_type)

    result = {} 
    txn_details = {}
    #print("get result: ", details)
    if (isinstance(details, dict)):
        result = {
            'header': 'API execution Success!',
            'icon': 'success',
            'message': 'Your test transaction has been successfully processed.'
        }
        txn_details = details
    else:
        result = {
            'header': 'Transaction Failed',
            'icon': 'fail',
            'message': details
        }

    return render_template('gateways/pp_show.html', details=txn_details, result=result, id_type=id_type)

##################### Python Server ###########################
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=True)
