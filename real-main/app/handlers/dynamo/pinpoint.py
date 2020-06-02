import logging

from app.models.user.enums import UserStatus

logger = logging.getLogger()


def update_pinpoint(pinpoint_client, user_id, old_user_item, new_user_item):
    # check if this was a user deletion
    if old_user_item and not new_user_item:
        pinpoint_client.delete_user_endpoints(user_id)
        return

    # check for a change of email, phone
    for dynamo_name, pinpoint_name in (('email', 'EMAIL'), ('phoneNumber', 'SMS')):
        value = new_user_item.get(dynamo_name, {}).get('S')
        if old_user_item.get(dynamo_name, {}).get('S') == value:
            continue
        if value:
            pinpoint_client.update_user_endpoint(user_id, pinpoint_name, value)
        else:
            pinpoint_client.delete_user_endpoint(user_id, pinpoint_name)

    # check if this was a change in user status
    status = new_user_item.get('userStatus', {}).get('S', UserStatus.ACTIVE)
    if old_user_item and old_user_item.get('userStatus', {}).get('S', UserStatus.ACTIVE) != status:
        if status == UserStatus.ACTIVE:
            pinpoint_client.enable_user_endpoints(user_id)
        if status == UserStatus.DISABLED:
            pinpoint_client.disable_user_endpoints(user_id)
        if status == UserStatus.DELETING:
            pinpoint_client.delete_user_endpoints(user_id)
