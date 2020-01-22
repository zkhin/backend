import json

from app.clients import GoogleClient

# the requests_mock parameter is auto-supplied, no need to even import the
# requests-mock library # https://requests-mock.readthedocs.io/en/latest/pytest.html


def test_get_verified_email_success(requests_mock):
    url = 'https://my-root-url/tokeninfo'
    client = GoogleClient(url)

    id_token = 'my-access-token'
    complete_url = f'{url}?id_token={id_token}'
    # this an actual real response, if it's not obvious
    mocked_contact_info = {
        "iss": "https://accounts.google.com",
        "azp": "400069738541-7kpcismu1l02ahibktn5ldrfqct23mb2.apps.googleusercontent.com",
        "aud": "400069738541-7kpcismu1l02ahibktn5ldrfqct23mb2.apps.googleusercontent.com",
        "sub": "101274498972592384425",
        "hd": "real.app",
        "email": "mike@real.app",
        "email_verified": "true",
        "at_hash": "vHojrhEDEK1fPNhEEm21mg",
        "name": "Mike Fogel",
        "picture": "https://lh3.googleusercontent.com/truncated.jpg",
        "given_name": "Mike",
        "family_name": "Fogel",
        "locale": "en",
        "iat": "1574788742",
        "exp": "1574792342",
        "alg": "RS256",
        "kid": "dee8d3dafbf31262ab9347d620383217afd96ca3",
        "typ": "JWT"
    }

    requests_mock.get(complete_url, text=json.dumps(mocked_contact_info))
    email = client.get_verified_email(id_token)
    assert email == 'mike@real.app'


def test_get_verified_email_not_verified(requests_mock):
    url = 'https://my-root-url/tokeninfo'
    client = GoogleClient(url)

    id_token = 'my-access-token'
    complete_url = f'{url}?id_token={id_token}'
    # an actual real response, if it's not obvious
    mocked_contact_info = {
        "email": "mike@real.app",
        "email_verified": "false",
    }

    requests_mock.get(complete_url, text=json.dumps(mocked_contact_info))
    email = client.get_verified_email(id_token)
    assert email is None
