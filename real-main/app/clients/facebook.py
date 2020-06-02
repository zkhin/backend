import requests


class FacebookClient:
    def __init__(self, api_root='https://graph.facebook.com'):
        self.api_root = api_root

    def get_verified_email(self, access_token):
        # https://developers.facebook.com/tools/explorer/
        # https://stackoverflow.com/questions/14280535/is-it-possible-to-check-if-an-email-is-confirmed-on-facebook
        # TODO: is there some way to check that the token was actually issued for our app?
        url = f'{self.api_root}/me'
        params = {
            'fields': 'email',
            'access_token': access_token,
        }
        resp = requests.get(url=url, params=params)
        return resp.json().get('email') if resp.status_code == 200 else None
