import requests


class GoogleClient:

    def __init__(self, url='https://oauth2.googleapis.com/tokeninfo'):
        self.url = url

    def get_verified_email(self, id_token):
        # https://developers.google.com/oauthplayground/
        # https://developers.google.com/identity/sign-in/web/backend-auth#calling-the-tokeninfo-endpoint
        # TODO: probably better to just decode the token rather than make a network call
        # TODO: check that the token was actually issued for our app
        params = {'id_token': id_token}
        resp = requests.get(url=self.url, params=params)
        body = resp.json() if resp.status_code == 200 else {}
        return body.get('email') if body.get('email_verified') == 'true' else None
