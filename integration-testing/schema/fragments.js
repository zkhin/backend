/* GraphQL query fragments */

import gql from 'graphql-tag'

export const chat = gql`
  fragment ChatFragment on Chat {
    chatId
    chatType
    name
    createdAt
    lastMessageActivityAt
    flagStatus
    messagesCount
    messagesViewedCount: messagesCount(viewedStatus: VIEWED)
    messagesUnviewedCount: messagesCount(viewedStatus: NOT_VIEWED)
    usersCount
    users {
      items {
        userId
      }
    }
  }
`

export const chatMessage = gql`
  fragment ChatMessageFragment on ChatMessage {
    messageId
    text
    textTaggedUsers {
      tag
      user {
        userId
      }
    }
    createdAt
    lastEditedAt
    chat {
      chatId
    }
    authorUserId
    author {
      userId
      username
      photo {
        url64p
      }
    }
  }
`

export const image = gql`
  fragment ImageFragment on Image {
    url
    url4k
    url1080p
    url480p
    url64p
    urlEla
    width
    height
    colors {
      r
      g
      b
    }
  }
`

export const video = gql`
  fragment VideoFragment on Video {
    urlMasterM3U8
    accessCookies {
      domain
      path
      expiresAt
      policy
      signature
      keyPairId
    }
  }
`

export const album = gql`
  fragment AlbumFragment on Album {
    albumId
    ownedBy {
      userId
    }
    createdAt
    name
    description
    art {
      ...ImageFragment
    }
    postCount
    postsLastUpdatedAt
    posts {
      items {
        postId
      }
    }
  }
  ${image}
`

export const card = gql`
  fragment CardFragment on Card {
    cardId
    title
    subTitle
    action
    thumbnail {
      ...ImageFragment
    }
  }
  ${image}
`

export const comment = gql`
  fragment CommentFragment on Comment {
    commentId
    commentedAt
    commentedBy {
      userId
    }
    text
    textTaggedUsers {
      tag
      user {
        userId
        username
      }
    }
    viewedStatus
    flagStatus
  }
`

export const textTaggedUser = gql`
  fragment TextTaggedUserFragment on TextTaggedUser {
    tag
    user {
      userId
      username
    }
  }
`

export const simpleUserFields = gql`
  fragment SimpleUserFields on User {
    username
    fullName
    displayName
    bio
    email
    phoneNumber
    dateOfBirth
    gender
    privacyStatus
    postCount
    followedStatus
    followerStatus
    followCountsHidden
    followedsCount
    followersCount
    followersRequestedCount: followersCount(followStatus: REQUESTED)
    languageCode
    themeCode
    blockedStatus
    blockerStatus
    acceptedEULAVersion
    adsDisabled
    commentsDisabled
    likesDisabled
    sharingDisabled
    verificationHidden
    postViewedByCount
    viewCountsHidden
    signedUpAt
    userStatus
    subscriptionLevel
    height
    subscriptionExpiresAt
    lastFoundContactsAt
    userDisableDatingDate
    matchGenders
    matchLocationRadius
    location {
      latitude
      longitude
      accuracy
    }
    matchAgeRange {
      min
      max
    }
    matchHeightRange {
      min
      max
    }
    datingStatus
    matchStatus
  }
`
