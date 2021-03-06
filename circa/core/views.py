from django.contrib import messages
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from core.email import listing_bought_seller_notification, admin_notification_of_sale, \
    listing_bought_buyer_notification
from core.models import Item, Listing, UserProfile, PromoCode
from core.forms import ItemListingForm, EditListingForm, PromoForm, AddressForm, EmailRequestForm
from core.keys import *
from core.payout import calc_payout, COMMISSION_BREAKEVEN, COMMISSION_FLAT, COMMISSION_MAX, COMMISSION_PERCENT
from core.zipcode import zipcodes
from decimal import *
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
import json
import stripe
import requests

import datetime


# Home page that shows items with associated listings that haven't already ended
def index(request):
    now = datetime.datetime.now()
    item_list = Item.objects.exclude(listing__isnull=True).exclude(listing__end_date__lte=now) \
        .order_by('?')
    if request.user.is_authenticated():
        all_user_items = Item.objects.filter(buyer=request.user)
        pending_num = 0
        for bought_item in all_user_items:
            if bought_item.listing.paid_for is True and bought_item.listing.address_confirmed is False:
                pending_num += 1
        context = {'items': item_list, 'pending_num': pending_num}

    else:
        context = {'items': item_list}

    return render(request, 'index.html', context)


# Displays home page, but with specific category items only
def category(request, category_name):
    if category_name in Item.CATEGORY_NAMES.keys():
        now = datetime.datetime.now()
        item_list = Item.objects.exclude(listing__isnull=True).exclude(listing__end_date__lte=now) \
            .filter(category=Item.CATEGORY_NAMES[category_name]).order_by('-pk')
        context = {'items': item_list, 'category': Item.CATEGORY_NAMES[category_name]}
        return render(request, 'index.html', context)
    else:
        return HttpResponseRedirect('/')


# Posting an item
@login_required
def sell(request):
    if request.method == 'POST':
        form = ItemListingForm(request.POST, request.FILES, seller=request.user)

        if form.is_valid():
            item = form.save()
            return HttpResponseRedirect('/listing/' + str(item.listing.id))
    else:
        form = ItemListingForm(seller=request.user)

    context = {'form': form, 'commission_percent': COMMISSION_PERCENT, 'commission_breakeven': COMMISSION_BREAKEVEN,
               'commission_flat': COMMISSION_FLAT, 'commission_max': COMMISSION_MAX}
    return render(request, 'sell.html', context)


@login_required
def edit_listing(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)
    item = listing.item

    # Listing already ended
    if listing.end_date and listing.end_date < datetime.datetime.now():
        return render(request, 'expired.html')

    # Listing is already paid for... shouldn't ever get here since end date should've passed, but just in case
    if listing.paid_for:
        return render(request, 'expired.html')

    # Some bro wants to edit a listing that is not his!
    if item.seller.id is not request.user.id:
        raise PermissionDenied

    if request.method == 'POST':
        form = EditListingForm(request.POST, listing=listing)

        if form.is_valid():
            form.save()
            return HttpResponseRedirect('/listing/' + str(listing.id))

    else:
        form = EditListingForm(
            initial={
                'title': item.title,
                'description': item.description,
                'category': item.category,
                'price': listing.price,
                'zipcode': listing.zipcode
            }, listing=listing)

    context = {'item': item, 'listing': listing, 'form': form}
    return render(request, 'edit_listing.html', context)

@login_required()
def delete_listing(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)
    item = listing.item

    #Some bro wants to delete a listing that is not his!
    if item.seller.id is not request.user.id:
        raise PermissionDenied

    if request.method == 'POST': #clicked delete button

        item.delete()
        listing.delete() #This should delete the item, but it's probably better to explicitly delete the item
        return HttpResponseRedirect('/items/') #redirects to user's currently listed items

    else:
        context = {'item': item, 'listing': listing}
        return render(request, 'delete_listing.html', context)


# URL with no slug, redirect to url with slug
def listing_detail_no_slug(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)
    return HttpResponseRedirect('/listing/' + str(listing.id) + '/' + listing.item.slug)


# Displays the requested listing along with info about listing item, or 404 page
def listing_detail(request, listing_id, listing_slug):
    listing = get_object_or_404(Listing, pk=listing_id)

    form = None
    item_sold = 0

    if request.user.is_authenticated:
        form = PromoForm(user=request.user, listing=listing)

    if listing.item.buyer:
        item_sold = 1

    if listing_slug != listing.item.slug:
        return HttpResponseRedirect('/listing/' + str(listing.id) + '/' + listing.item.slug)

    if request.method == 'POST':
        token = request.POST.get('stripeToken', False)

        if token:
            return handle_stripe(request, listing, token)

        elif "free" in request.POST:
            return update_listing(listing, request, promo_code=None)

        else:
            form = PromoForm(request.POST, user=request.user, listing=listing)
            if form.is_valid():
                form.save()

    item = listing.item
    amount = int(listing.price * 100)
    stripe_amount = json.dumps(amount)
    context = {'listing': listing, 'item': item, 'amount': stripe_amount, 'stripe_key': public_key(),
               'form': form, 'item_sold': item_sold}

    break_even = .5
    if request.user.is_authenticated and listing.promocode_set.all().count() > 0:
        for promo in listing.promocode_set.all():
            if promo.user.id is request.user.id:
                if listing.price - promo.value < break_even:
                    context['free'] = 1

                else:
                    context['discount'] = promo.value
                    context['discounted_price'] = listing.price - promo.value
                    context['discounted_price_amount'] = (listing.price - promo.value) * Decimal(100)

                break

    return render(request, 'listing_detail.html', context)


def request_email(request):
    if request.method == 'POST':
        form = EmailRequestForm(request.POST)
        if form.is_valid():
            return HttpResponseRedirect(reverse('social:complete', args=("facebook",)) +
                                        '?email=' + form.cleaned_data['email'])
    else:
        form = EmailRequestForm()
    return render(request, 'request_email.html', {'form': form})


# Shows all outstanding, unpaid listings for user
@login_required
def pending(request):
    if not request.user.userprofile.address:
        return HttpResponseRedirect('/address/?next=/pending/')

    # find listings where user is the highest offer user, payment has not been received, and have already ended
    items = []
    listings = Listing.objects.filter(paid_for=True).filter(address_confirmed=False)
    for listing in listings:
        try:
            if listing.item.buyer and listing.item.buyer.id is request.user.id:
                items.append(listing.item)

        except ObjectDoesNotExist:  # listing has no related item
            pass

    return render(request, 'pending.html', {'items': items})


def terms(request):
    return render(request, 'terms.html')


def about(request):
    context = {'zipcodes': zipcodes(), 'zip_len': len(zipcodes())}
    return render(request, 'about.html', context)


@login_required
def confirm(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)

    # User is trying to pay for someone else's listing
    if request.user.id is not listing.item.buyer.id:
        raise PermissionDenied

    # User already confirmed item
    if listing.address_confirmed:
        return render(request, 'expired.html')

    if request.method == 'POST':
        if 'change' in request.POST:
            return HttpResponseRedirect('/address/?next=/confirm/' + str(listing.id))

        else:
            listing.address_confirmed = True
            listing.save()

            listing_bought_buyer_notification(listing)
            listing_bought_seller_notification(listing)
            admin_notification_of_sale(listing)

            return HttpResponseRedirect('/success/')

    if request.user.userprofile.address:
        context = {'address': request.user.userprofile.address}
        return render(request, 'confirm.html', context)

    else:
        return HttpResponseRedirect('/address/?next=/confirm/' + str(listing.id))


def success(request):
    return render(request, 'success.html')


def help(request):
    context = {'zipcodes': zipcodes(), 'zip_len': len(zipcodes())}
    return render(request, 'help.html', context)


@login_required
def dashboard(request):
    now = datetime.datetime.now()
    user = request.user
    earnings_num = 0
    active_items_num = 0
    items = Item.objects.filter(seller=user)
    for item in items:
        if item.listing:
            earnings_num += item.listing.payout

            # Offer on listing, but still time left
            if item.listing.end_date and item.listing.end_date > datetime.datetime.now():
                active_items_num += 1

            # Listing over but not paid for yet
            if item.listing.end_date and item.listing.end_date < now and not item.listing.paid_for:
                active_items_num += 1

            # Listed item, but no offers
            if not item.listing.end_date:
                active_items_num += 1
    bought = Item.objects.filter(buyer=user)

    context = {'earnings': earnings_num, 'orders': bought, 'active_items': active_items_num}
    return render(request, 'dashboard.html', context)


@login_required
def offers(request):  # not very DRY
    now = datetime.datetime.now()
    user = request.user
    listings_list = Listing.objects.filter(current_offer_user=user).filter(end_date__gt=now)
    context = {'listings': listings_list}
    return render(request, 'offers.html', context)


@login_required
def earnings(request):  # not very DRY
    total_earnings = 0
    user = request.user
    items = Item.objects.filter(seller=user)
    items_list = []
    for item in items:
        if item.listing and item.listing.payout > 0:
            items_list.append(item)
            total_earnings += item.listing.payout
    context = {'items': items_list, 'earnings': total_earnings}
    return render(request, 'earnings.html', context)


# Remove from production (teehee)
def todo(request):
    return render(request, 'todo.html')


# Active items for seller: items where offer is accepted but not sold, and items not yet sold
@login_required
def active_items(request):
    now = datetime.datetime.now()
    user = request.user
    items_list = Item.objects.filter(seller=user)
    active_items_list = []
    unpaid_items_list = []
    no_offers_items_list = []
    for item in items_list:
        if item.listing:
            if item.listing.end_date:
                # Active listing with offers
                if item.listing.end_date > now:
                    active_items_list.append(item)

                # Offer hasn't been paid for
                elif item.listing.end_date < now and not item.listing.paid_for:
                    unpaid_items_list.append(item)

            # listed item with no end date means no offers have been made
            else:
                no_offers_items_list.append(item)

    context = {'active_items': active_items_list, 'unpaid_items': unpaid_items_list, 'no_offers': no_offers_items_list}
    return render(request, 'active_items.html', context)


@login_required
def address(request):
    if request.method == 'POST':
        form = AddressForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(request.POST.get('next', '/'))
    else:
        if request.user.userprofile.address:
            addr = request.user.userprofile.address
            form = AddressForm(initial={
                'address_line_1': addr.address_line_1,
                'address_line_2': addr.address_line_2,
                'city': addr.city,
                'state': addr.state,
                'zipcode': addr.zipcode,
                'special_instructions': addr.special_instructions
            }, user=request.user)

        else:
            form = AddressForm(initial={
                'state': AddressForm.INITIAL_STATE
            }, user=request.user)

    context = {'form': form, 'next': request.GET.get('next', '/')}
    return render(request, 'address.html', context)


# ------ HELPER METHODS -------


def update_listing(listing, request, promo_code):
    listing.item.buyer = request.user
    listing.item.save()
    listing.end_date = datetime.datetime.now()
    listing.paid_for = True
    listing.payout = calc_payout(listing.price)
    listing.save()
    if promo_code is not None:
        promo_code.redeemed = True
        promo_code.save()

    if request.user.userprofile.address:
        return HttpResponseRedirect('/confirm/' + str(listing.id))

    else:
        return HttpResponseRedirect('/address/?next=/confirm/' + str(listing.id))


def handle_stripe(request, listing, token):
    stripe.api_key = secret_key()
    promo_code = None
    amount_in_cents = -1
    if listing.promocode_set.all().count() > 0:
        for promo in listing.promocode_set.all():
            if promo.user.id is request.user.id:
                promo_code = promo
                amount_in_cents = int((listing.price - promo.value) * 100)
                break

    if amount_in_cents == -1:
        amount_in_cents = int(listing.price * 100)

    try:
        stripe.Charge.create(
            amount=amount_in_cents,
            currency="usd",
            source=token,
            description="Circa Buy Now " + str(listing.id) + ": " + str(listing.item.title)
        )
        update_listing(listing, request, promo_code)

        if request.user.userprofile.address:
            return HttpResponseRedirect('/confirm/' + str(listing.id))

        else:
            return HttpResponseRedirect('/address/?next=/confirm/' + str(listing.id))

    except stripe.error.CardError:
        messages.error(request, 'Your credit card was declined.  If you\'re sure that your card is valid, '
                                'the problem may be with our payment processing system.  Wait an hour or '
                                'so and try again.  If the problem persists, please contact us at '
                                'support@usecirca.com so we can help sort out the issue.')
        return HttpResponseRedirect(request.path)