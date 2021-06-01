import gql from 'graphql-tag'

import * as fragments from './fragments.js'

export const onNotification = gql`
  subscription OnNotification($userId: ID!) {
    onNotification(userId: $userId) {
      userId
      type
      followedUserId
      matchUserId
      postId
      userChatsWithUnviewedMessagesCount
    }
  }
`

export const onCardNotification = gql`
  subscription OnCardNotification($userId: ID!) {
    onCardNotification(userId: $userId) {
      userId
      type
      card {
        cardId
        title
        subTitle
        action
      }
    }
  }
`

export const onChatMessageNotification = gql`
  subscription OnChatMessageNotification($userId: ID!) {
    onChatMessageNotification(userId: $userId) {
      userId
      type
      message {
        ...ChatMessageFragment
      }
    }
  }
  ${fragments.chatMessage}
`
