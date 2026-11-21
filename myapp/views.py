from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import CollectionRequestForm, LocationForm, ResidentRegistrationForm


def home(request):
    """Public landing page."""
    return render(request, 'home.html')


def register(request):
    """Resident self-registration."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = ResidentRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created. You can now log in.')
            return redirect('login')
    else:
        form = ResidentRegistrationForm()

    return render(request, 'register.html', {'form': form})


@login_required
def dashboard(request):
    """Temporary landing page after login. Replaced by role dashboards in Step 9."""
    return render(request, 'dashboard.html')



@login_required
def location_list(request):
    locations = request.user.locations.all()
    return render(request, 'location_list.html', {'locations': locations})


@login_required
def location_create(request):
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid():
            location = form.save(commit=False)
            location.resident = request.user
            location.save()
            messages.success(request, 'Location added.')
            return redirect('location_list')
    else:
        form = LocationForm()
    return render(request, 'location_form.html', {'form': form})



@login_required
def request_create(request):
    if not request.user.is_resident:
        messages.error(request, 'Only residents can request a collection.')
        return redirect('dashboard')

    # A request needs a location, so send new residents to add one first
    if not request.user.locations.exists():
        messages.error(request, 'Please add a collection location first.')
        return redirect('location_create')

    if request.method == 'POST':
        form = CollectionRequestForm(request.POST, user=request.user)
        if form.is_valid():
            collection = form.save(commit=False)
            collection.resident = request.user
            collection.save()
            messages.success(request, 'Collection request submitted.')
            return redirect('request_list')
    else:
        form = CollectionRequestForm(user=request.user)
    return render(request, 'request_form.html', {'form': form})


@login_required
def request_list(request):
    requests_made = request.user.collection_requests.select_related(
        'location', 'package', 'waste_type',
    )
    return render(request, 'request_list.html', {'requests_made': requests_made})

import json
from decimal import Decimal

import requests
from django.db import transaction
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import mpesa
from .models import Payment




@login_required
@require_POST
def pay_request(request, pk):
    """Start an M-Pesa STK Push for one of the resident's requests."""
    collection = get_object_or_404(request.user.collection_requests, pk=pk)

    if collection.is_paid:
        messages.info(request, 'This request is already paid.')
        return redirect('request_list')

    if not request.user.phone_number:
        messages.error(request, 'Add a phone number to your account first.')
        return redirect('request_list')

    if not settings.MPESA_CALLBACK_URL:
        messages.error(request, 'Payments are not configured yet (callback URL missing).')
        return redirect('request_list')

    phone = mpesa.format_phone(request.user.phone_number)

    try:
        result = mpesa.stk_push(
            phone=phone,
            amount=collection.amount,
            reference=f'TAKA{collection.pk}',
            description='Waste collection',
        )
    except requests.RequestException:
        messages.error(request, 'Could not reach M-Pesa. Please try again.')
        return redirect('request_list')

    if result.get('ResponseCode') == '0':
        Payment.objects.create(
            request=collection,
            resident=request.user,
            amount=collection.amount,
            phone_number=phone,
            checkout_request_id=result['CheckoutRequestID'],
        )
        messages.success(request, 'Check your phone and enter your M-Pesa PIN to complete payment.')
    else:
        messages.error(request, 'M-Pesa could not start the payment. Please try again.')
    return redirect('request_list')


@csrf_exempt
@require_POST
def mpesa_callback(request):
    """Safaricom calls this with the payment result. No login or CSRF token is possible here."""
    ok = JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})

    try:
        data = json.loads(request.body)['Body']['stkCallback']
        checkout_id = data['CheckoutRequestID']
        result_code = int(data['ResultCode'])
    except (ValueError, KeyError, TypeError):
        return ok

    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(
            checkout_request_id=checkout_id,
        ).first()

        # Unknown transaction, or already processed (replayed callback)
        if payment is None or payment.status != Payment.Status.PENDING:
            return ok

        payment.result_description = str(data.get('ResultDesc', ''))[:255]

        if result_code == 0:
            items = {
                i.get('Name'): i.get('Value')
                for i in data.get('CallbackMetadata', {}).get('Item', [])
            }
            paid = Decimal(str(items.get('Amount', '0')))
            receipt = items.get('MpesaReceiptNumber')

            # Only accept if the amount matches what we asked for
            if receipt and paid == payment.amount:
                payment.status = Payment.Status.SUCCESS
                payment.mpesa_receipt_number = receipt
            else:
                payment.status = Payment.Status.FAILED
                payment.result_description = 'Amount or receipt did not match.'
        else:
            payment.status = Payment.Status.FAILED

        payment.save()

    return ok