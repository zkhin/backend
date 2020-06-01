def update_elasticsearch(elasticsearch_client, old_user_item, new_user_item):
    # if we're manually rebuilding the index, treat everything as new
    new_reindexed_at = new_user_item.get('lastManuallyReindexedAt', {}).get('S')
    old_reindexed_at = old_user_item.get('lastManuallyReindexedAt', {}).get('S')
    if new_reindexed_at and new_reindexed_at != old_reindexed_at:
        old_user_item = {}

    if new_user_item and old_user_item:
        elasticsearch_client.update_user(old_user_item, new_user_item)
    if new_user_item and not old_user_item:
        elasticsearch_client.add_user(new_user_item)
    if not new_user_item and old_user_item:
        elasticsearch_client.delete_user(old_user_item)
