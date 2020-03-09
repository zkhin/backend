/* GraphQL query fragments */

const gql = require('graphql-tag')


module.exports.image = gql`
  fragment ImageFragment on Image {
    url
    url4k
    url1080p
    url480p
    url64p
    width
    height
    colors {
      r
      g
      b
    }
  }
`

module.exports.video = gql`
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

module.exports.album = gql`
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
    url
    url4k
    url1080p
    url480p
    url64p
    postCount
    postsLastUpdatedAt
    posts {
      items {
        postId
      }
    }
  }
  ${module.exports.image}
`

module.exports.comment = gql`
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
  }
`

module.exports.mediaObject = gql`
  fragment MediaObjectFragment on MediaObject {
    mediaId
    mediaStatus
    mediaType
    isVerified
    uploadUrl
    url
    url4k
    url1080p
    url480p
    url64p
    height
    width
    colors {
      r
      g
      b
    }
  }
`

module.exports.textTaggedUser = gql`
  fragment TextTaggedUserFragment on TextTaggedUser {
    tag
    user {
      userId
      username
    }
  }
`

module.exports.simpleUserFields = gql`
  fragment SimpleUserFields on User {
    username
    fullName
    photoUrl
    photoUrl64p
    photoUrl480p
    photoUrl1080p
    photoUrl4k
    bio
    email
    phoneNumber
    privacyStatus
    postCount
    followedStatus
    followerStatus
    followCountsHidden
    followedCount
    followerCount
    languageCode
    themeCode
    blockedStatus
    blockerStatus
    acceptedEULAVersion
    commentsDisabled
    likesDisabled
    sharingDisabled
    verificationHidden
    postViewedByCount
    viewCountsHidden
    signedUpAt
  }
`
