import codecs
import logging
import os

import boto3

logger = logging.getLogger()

SES_EMAIL_SENDER_ADDRESS = os.environ.get('SES_EMAIL_SENDER_ADDRESS')
SES_EMAIL_SENDER_ARN = os.environ.get('SES_EMAIL_SENDER_ARN')


class SesClient:
    def __init__(
        self,
        SES_EMAIL_SENDER_ADDRESS=SES_EMAIL_SENDER_ADDRESS,
        SES_EMAIL_SENDER_ARN=SES_EMAIL_SENDER_ARN,
    ):
        self.ses_client = boto3.client('ses')
        self.ses_email_sender_address = SES_EMAIL_SENDER_ADDRESS
        self.ses_email_sender_arn = SES_EMAIL_SENDER_ARN

    def send_email(self, recipients, template_name, subject):
        try:
            template = codecs.open(
                os.path.join(os.path.dirname(__file__), '..', '..', 'email_templates', f'{template_name}.html'),
                'r',
            )
            self.ses_client.send_email(
                Destination={
                    'ToAddresses': recipients,
                },
                Message={
                    'Body': {
                        'Html': {
                            'Charset': 'UTF-8',
                            'Data': template.read(),
                        },
                    },
                    'Subject': {
                        'Charset': 'UTF-8',
                        'Data': subject,
                    },
                },
                Source=self.ses_email_sender_address,
                SourceArn=self.ses_email_sender_arn,
            )
        except Exception as err:
            logger.warning(str(err))
