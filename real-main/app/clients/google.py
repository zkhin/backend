import cachecontrol
import google.auth.transport.requests as google_requests
import google.oauth2.id_token as google_id_token
import requests


class GoogleClient:
    def __init__(self, client_ids_getter):
        self.client_ids_getter = client_ids_getter
        self.cached_session = cachecontrol.CacheControl(requests.session())

    @property
    def client_ids(self):
        if not hasattr(self, '_client_ids'):
            self._client_ids = self.client_ids_getter()
        return self._client_ids

    def get_verified_email(self, id_token):
        "Verify the token, parse and return a verified email from it"
        # https://developers.google.com/oauthplayground/
        # https://developers.google.com/identity/sign-in/web/backend-auth#calling-the-tokeninfo-endpoint
        # https://googleapis.dev/python/google-auth/latest/reference/google.oauth2.id_token.html
        # raises ValueError on expired token
        id_info = google_id_token.verify_oauth2_token(id_token, google_requests.Request(session=self.cached_session))
        if id_info.get('aud') not in self.client_ids.values():
            raise ValueError(f'Token wrong audience: `{id_info["aud"]}`')
        if not id_info.get('email_verified') or not id_info.get('email'):
            raise ValueError('Token does not contain verified email')
        return id_info['email']
