const gql = require('graphql-tag')

const fragments = require('./fragments.js')

module.exports.onChatMessageNotification = gql`
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

module.exports.onPostNotification = gql`
  subscription OnPostNotification($userId: ID!) {
    onPostNotification(userId: $userId) {
      userId
      type
      post {
        postId
        postStatus
        isVerified
      }
    }
  }
`
