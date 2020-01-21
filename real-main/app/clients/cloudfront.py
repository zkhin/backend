import datetime
import os
import urllib

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from botocore.signers import CloudFrontSigner

CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')


class CloudFrontClient:

    def __init__(self, key_pair_getter, domain=CLOUDFRONT_DOMAIN):
        assert domain, "CloudFront domain is required"
        self.domain = domain
        self.key_pair_getter = key_pair_getter
        self._cloudfront_signer = None

    def get_cloudfront_signer(self):
        "Return a tuple of (key id, serialized private key)"
        if not self._cloudfront_signer:
            key_pair = self.key_pair_getter()
            key_id = key_pair['keyId']

            # the private key format requires newlines after the header and before the footer
            # and the secrets manager doesn't seem to play well with newlines
            pk_string = f"-----BEGIN RSA PRIVATE KEY-----\n{key_pair['privateKey']}\n-----END RSA PRIVATE KEY-----"
            pk_bytes = bytearray(pk_string, 'utf-8')
            pk = serialization.load_pem_private_key(pk_bytes, password=None, backend=default_backend())

            def rsa_signer(message):
                return pk.sign(message, padding.PKCS1v15(), hashes.SHA1())

            self._cloudfront_signer = CloudFrontSigner(key_id, rsa_signer)

        return self._cloudfront_signer

    def generate_presigned_url(self, path, methods, valid_for=datetime.timedelta(hours=1)):
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudfront.html#examples
        qs = urllib.parse.urlencode([('Method', m) for m in methods])
        url = f'https://{self.domain}/{path}?{qs}'
        expires_at = datetime.datetime.utcnow() + valid_for
        cloudfront_signer = self.get_cloudfront_signer()
        return cloudfront_signer.generate_presigned_url(url, date_less_than=expires_at)
