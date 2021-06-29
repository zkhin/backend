from decimal import BasicContext, Decimal
from random import random
from uuid import uuid4

import pytest
import requests
import requests_mock

from app.clients import RealTransactionsClient
from app.clients.real_transactions import InsufficientFundsException

api_host = 'the.api.host'
api_stage = 'the-stage'
api_region = 'the-region'

# https://github.com/real-social-media/transactions/blob/83bd05b/serverless.yml#L139
# https://github.com/real-social-media/transactions/blob/83bd05b/serverless.yml#L150
endpoint_urls = {
    'pay_for_ad_view': f'https://{api_host}/{api_stage}/pay_user_for_advertisement',
    'pay_for_post_view': f'https://{api_host}/{api_stage}/pay_for_post_view',
}


@pytest.fixture
def client():
    yield RealTransactionsClient(
        api_host=api_host,
        api_stage=api_stage,
        api_region=api_region,
    )


# https://github.com/DavidMuller/aws-requests-auth/issues/49#issuecomment-543297856
@pytest.fixture
def mock_env_aws_auth(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "mock_key_id")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "mock_secret")


@pytest.mark.parametrize('amount', [0.1, 1])
@pytest.mark.parametrize('func_name, ticker', [['pay_for_ad_view', None], ['pay_for_post_view', 'REAL']])
def test_amount_must_be_a_decimal(client, amount, func_name, ticker):
    args = [str(uuid4()), str(uuid4()), str(uuid4()), amount]
    if ticker:
        args.append(ticker)
    target = getattr(client, func_name)
    with pytest.raises(AssertionError, match="'amount' must be a Decimal"):
        target(*args)


@pytest.mark.parametrize('func_name, ticker', [['pay_for_ad_view', None], ['pay_for_post_view', 'REAL']])
def test_with_disabled_true(func_name, ticker):
    client = RealTransactionsClient(api_host=api_host, api_stage=api_stage, api_region=api_region, disabled=True)
    target = getattr(client, func_name)
    args = [str(uuid4()), str(uuid4()), str(uuid4()), Decimal(random()).normalize(context=BasicContext)]
    if ticker:
        args.append(ticker)
    with requests_mock.Mocker() as m:
        target(*args)
    assert len(m.request_history) == 0


def test_pay_for_ad_view_sends_correct_request(client, mock_env_aws_auth):
    url = endpoint_urls['pay_for_ad_view']
    viewer_id = str(uuid4())
    ad_post_owner_id = str(uuid4())
    ad_post_id = str(uuid4())
    amount = Decimal(random()).normalize(context=BasicContext)
    with requests_mock.Mocker() as m:
        m.post(url, status_code=200)
        client.pay_for_ad_view(viewer_id, ad_post_owner_id, ad_post_id, amount)
    assert len(m.request_history) == 1
    assert m.request_history[0].method == 'POST'
    assert m.request_history[0].json() == {
        'advertiser_uuid': ad_post_owner_id,
        'viewer_uuid': viewer_id,
        'amount': str(amount),
        'description': f'For view of ad with post id: {ad_post_id}',
    }


def test_pay_for_post_view_sends_correct_request(client, mock_env_aws_auth):
    url = endpoint_urls['pay_for_post_view']
    viewer_id = str(uuid4())
    post_owner_id = str(uuid4())
    post_id = str(uuid4())
    ticker = str(uuid4())
    amount = Decimal(random()).normalize(context=BasicContext)
    with requests_mock.Mocker() as m:
        m.post(url, status_code=200)
        client.pay_for_post_view(viewer_id, post_owner_id, post_id, amount, ticker)
    assert len(m.request_history) == 1
    assert m.request_history[0].method == 'POST'
    assert m.request_history[0].json() == {
        'post_owner_uuid': post_owner_id,
        'viewer_uuid': viewer_id,
        'post_uuid': post_id,
        'amount': str(amount),
        'ticker': ticker,
    }


@pytest.mark.parametrize('func_name, ticker', [['pay_for_ad_view', None], ['pay_for_post_view', 'REAL']])
def test_handles_error_response(client, mock_env_aws_auth, func_name, ticker):
    url = endpoint_urls[func_name]
    failure_status = 400
    failure_response = {'message': 'Failed to process request', 'status': -2}
    args = [str(uuid4()), str(uuid4()), str(uuid4()), Decimal('0.01')]
    if ticker:
        args.append(ticker)
    target = getattr(client, func_name)
    with requests_mock.Mocker() as m:
        m.post(url, status_code=failure_status, json=failure_response)
        with pytest.raises(requests.exceptions.HTTPError, match=str(failure_status)):
            target(*args)


@pytest.mark.parametrize('func_name, ticker', [['pay_for_ad_view', None], ['pay_for_post_view', 'REAL']])
def test_handles_notenoughfunds_error_response(client, mock_env_aws_auth, func_name, ticker):
    url = endpoint_urls[func_name]
    failure_status = 400
    failure_response = {'exception': 'NotEnoughFundsException'}
    args = [str(uuid4()), str(uuid4()), str(uuid4()), Decimal('0.01')]
    if ticker:
        args.append(ticker)
    target = getattr(client, func_name)
    with requests_mock.Mocker() as m:
        m.post(url, status_code=failure_status, json=failure_response)
        with pytest.raises(InsufficientFundsException):
            target(*args)


@pytest.mark.parametrize('func_name, ticker', [['pay_for_ad_view', None], ['pay_for_post_view', 'REAL']])
def test_handles_success_response(client, mock_env_aws_auth, func_name, ticker):
    url = endpoint_urls[func_name]
    success_status = 200
    success_response = {'message': 'ok', 'status': 0}
    args = [str(uuid4()), str(uuid4()), str(uuid4()), Decimal('0.01')]
    if ticker:
        args.append(ticker)
    target = getattr(client, func_name)
    with requests_mock.Mocker() as m:
        m.post(url, status_code=success_status, json=success_response)
        target(*args)  # silently succeeds
