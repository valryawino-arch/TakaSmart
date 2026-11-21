import base64
from datetime import datetime

import requests
from django.conf import settings


def _base_url():
    if settings.MPESA_ENV == 'sandbox':
        return 'https://sandbox.safaricom.co.ke'
    return 'https://api.safaricom.co.ke'


def format_phone(phone):
    """Turn 0712345678 or +254712345678 into 254712345678."""
    phone = phone.strip().replace('+', '').replace(' ', '')
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    return phone


def get_access_token():
    """Ask Safaricom for a temporary token using our key and secret."""
    response = requests.get(
        f'{_base_url()}/oauth/v1/generate?grant_type=client_credentials',
        auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()['access_token']


def stk_push(phone, amount, reference, description):
    """Send the payment prompt to the resident's phone."""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = base64.b64encode(
        f'{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}'.encode()
    ).decode()

    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        'Amount': int(amount),
        'PartyA': phone,
        'PartyB': settings.MPESA_SHORTCODE,
        'PhoneNumber': phone,
        'CallBackURL': settings.MPESA_CALLBACK_URL,
        'AccountReference': reference,
        'TransactionDesc': description,
    }
    response = requests.post(
        f'{_base_url()}/mpesa/stkpush/v1/processrequest',
        json=payload,
        headers={'Authorization': f'Bearer {get_access_token()}'},
        timeout=30,
    )
    return response.json()