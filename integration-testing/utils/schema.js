/* GraphQL schema
 *
 * Note: this is **not** how this should be done by clients of the API!
 *
 * These queries and mutations are requesting many fields that are not needed for each call.
 * This is great for the testing suite (exercises more paths through the code, more opportunities for failure)
 * but in production this will just generate more load and higher latency.
 *
 * Clients of the api, outside of the test suite, should request minimal fields from the api for each call.
 */

const gql = require('graphql-tag')

module.exports.self = gql(`query Self ($anonymouslyLikedPostsLimit: Int, $onymouslyLikedPostsLimit: Int) {
  self {
    userId
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
    blockedAt
    blockerAt
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
    anonymouslyLikedPosts (limit: $anonymouslyLikedPostsLimit) {
      items {
        postId
        mediaObjects {
          mediaId
          url
        }
      }
    }
    onymouslyLikedPosts (limit: $onymouslyLikedPostsLimit) {
      items {
        postId
        mediaObjects {
          mediaId
          url
        }
      }
    }
    followerUsers {
      items {
        userId
      }
    }
    followedUsers {
      items {
        userId
      }
    }
    blockedUsers {
      items {
        userId
        blockedAt
        blockedStatus
      }
    }
    albumCount
    albums {
      items {
        albumId
        ownedBy {
          userId
        }
        name
        description
        createdAt
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
    }
  }
}`)

module.exports.user = gql(`query User ($userId: ID!) {
  user (userId: $userId) {
    userId
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
    blockedAt
    blockerAt
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
    anonymouslyLikedPosts {
      items {
        postId
        mediaObjects {
          mediaId
          url
        }
      }
    }
    onymouslyLikedPosts {
      items {
        postId
        mediaObjects {
          mediaId
          url
        }
      }
    }
    followerUsers {
      items {
        userId
      }
    }
    followedUsers {
      items {
        userId
      }
    }
    blockedUsers {
      items {
        userId
        blockedAt
        blockedStatus
      }
    }
    albumCount
    albums {
      items {
        albumId
        ownedBy {
          userId
        }
        createdAt
        name
        description
        postCount
        postsLastUpdatedAt
        posts {
          items {
            postId
          }
        }
      }
    }
  }
}`)

module.exports.createCognitoOnlyUser = gql(
  `mutation CreateCognitoOnlyUser ($username: String!, $fullName: String) {
    createCognitoOnlyUser (username: $username, fullName: $fullName) {
      userId
      username
      fullName
      email
      phoneNumber
      signedUpAt
    }
  }`
)

module.exports.createGoogleUser = gql(
  `mutation CreateGoogleUser ($username: String!, $fullName: String, $googleIdToken: String!) {
    createGoogleUser (username: $username, fullName: $fullName, googleIdToken: $googleIdToken) {
      userId
      username
      fullName
      email
    }
  }`
)

module.exports.createFacebookUser = gql(
  `mutation CreateFacebookUser ($username: String!, $fullName: String, $facebookAccessToken: String!) {
    createFacebookUser (username: $username, fullName: $fullName, facebookAccessToken: $facebookAccessToken) {
      userId
      username
      fullName
      email
    }
  }`
)

module.exports.searchUsers = gql(`query SearchUsers ($searchToken: String!) {
  searchUsers (searchToken: $searchToken) {
    items {
      userId
      username
      fullName
      photoUrl
    }
  }
}`)

module.exports.setUsername = gql(`mutation SetUsername ($username: String!) {
  setUserDetails (username: $username) {
    userId
    username
  }
}`)

module.exports.setUserPrivacyStatus = gql(`mutation SetUserPrivacyStatus ($privacyStatus: PrivacyStatus!) {
  setUserDetails (privacyStatus: $privacyStatus) {
    userId
    privacyStatus
    followedCount
    followerCount
  }
}`)

module.exports.setUserAcceptedEULAVersion = gql(`mutation SetUserEULAVersion ($version: String!) {
  setUserAcceptedEULAVersion (version: $version) {
    userId
    acceptedEULAVersion
  }
}`)


module.exports.setUserFollowCountsHidden = gql(`mutation SetUserFollowCountsHidden ($value: Boolean!) {
  setUserDetails (followCountsHidden: $value) {
    userId
    followCountsHidden
  }
}`)

module.exports.setUserViewCountsHidden = gql(`mutation SetUserViewCountsHidden ($value: Boolean!) {
  setUserDetails (viewCountsHidden: $value) {
    userId
    viewCountsHidden
  }
}`)

module.exports.setUserDetails = gql(`mutation SetUserDetails ($bio: String, $fullName: String, $photoMediaId: ID) {
  setUserDetails (bio: $bio, fullName: $fullName, photoMediaId: $photoMediaId) {
    userId
    bio
    fullName
    photoUrl
    photoUrl64p
    photoUrl480p
    photoUrl1080p
    photoUrl4k
  }
}`)

module.exports.setUserLanguageCode = gql(`mutation SetUserLanguageCode ($languageCode: String) {
  setUserDetails (languageCode: $languageCode) {
    userId
    languageCode
  }
}`)

module.exports.setUserThemeCode = gql(`mutation SetUserThemeCode ($themeCode: String) {
  setUserDetails (themeCode: $themeCode) {
    userId
    themeCode
  }
}`)

module.exports.setUserMentalHealthSettings = gql(
  `mutation SetUserCommentsDisabled (
    $commentsDisabled: Boolean,
    $likesDisabled: Boolean,
    $sharingDisabled: Boolean,
    $verificationHidden: Boolean,
  ) {
    setUserDetails (
      commentsDisabled: $commentsDisabled,
      likesDisabled: $likesDisabled,
      sharingDisabled: $sharingDisabled,
      verificationHidden: $verificationHidden,
    ) {
      userId
      commentsDisabled
      likesDisabled
      sharingDisabled
      verificationHidden
    }
  }`
)

module.exports.updateUserContactInfo = gql(`mutation SetUserContactInfo ($accessToken: String!) {
  updateUserContactInfo (authProvider: COGNITO, accessToken: $accessToken) {
    userId
    email
    phoneNumber
  }
}`)

module.exports.resetUser = gql(`mutation ResetUser ($newUsername: String) {
  resetUser (newUsername: $newUsername) {
    userId
    username
    fullName
  }
}`)

module.exports.followUser = gql(`mutation FollowUser ($userId: ID!) {
  followUser (userId: $userId) {
    userId
    followedStatus
    followerCount
  }
}`)

module.exports.unfollowUser = gql(`mutation UnfollowUser ($userId: ID!) {
  unfollowUser (userId: $userId) {
    userId
    followedStatus
    followerCount
  }
}`)

module.exports.acceptFollowerUser = gql(`mutation AcceptFollowerUser ($userId: ID!) {
  acceptFollowerUser (userId: $userId) {
    userId
    followerStatus
    followerCount
  }
}`)

module.exports.denyFollowerUser = gql(`mutation DenyFollowerUser ($userId: ID!) {
  denyFollowerUser (userId: $userId) {
    userId
    followerStatus
    followerCount
  }
}`)

module.exports.blockUser = gql(`mutation BlockUser ($userId: ID!) {
  blockUser (userId: $userId) {
    userId
    blockedAt
    blockedStatus
    username
    photoUrl
    privacyStatus
    followedStatus
    followerStatus
    followedCount
    followerCount
    postCount
    fullName
    themeCode
    bio
    email
    phoneNumber
    languageCode
  }
}`)

module.exports.unblockUser = gql(`mutation UnblockUser ($userId: ID!) {
  unblockUser (userId: $userId) {
    userId
    blockedAt
    blockedStatus
    username
    photoUrl
    privacyStatus
    followedStatus
    followerStatus
    followedCount
    followerCount
    postCount
    fullName
    themeCode
    bio
    email
    phoneNumber
    languageCode
  }
}`)

module.exports.addTextOnlyPost = gql(`mutation AddTextOnlyPost (
  $postId: ID!,
  $albumId: ID,
  $text: String,
  $lifetime: String,
  $commentsDisabled: Boolean,
  $likesDisabled: Boolean,
  $sharingDisabled: Boolean,
  $verificationHidden: Boolean,
) {
  addPost (
    postId: $postId,
    albumId: $albumId,
    text: $text,
    lifetime: $lifetime,
    commentsDisabled: $commentsDisabled,
    likesDisabled: $likesDisabled,
    sharingDisabled: $sharingDisabled,
    verificationHidden: $verificationHidden,
  ) {
    postId
    postedAt
    postStatus
    expiresAt
    album {
      albumId
    }
    text
    textTaggedUsers {
      tag
      user {
        userId
        username
      }
    }
    mediaObjects {
      mediaId
    }
    postedBy {
      userId
      username
      postCount
    }
    commentsDisabled
    commentCount
    comments {
      items {
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
          }
        }
      }
    }
    likesDisabled
    sharingDisabled
    verificationHidden
  }
}`)

module.exports.addOneMediaPost = gql(`mutation AddOneMediaPost (
  $postId: ID!,
  $mediaId: ID!,
  $albumId: ID,
  $mediaType: MediaObjectType!,
  $text: String,
  $lifetime: String
  $takenInReal: Boolean
  $originalFormat: String,
  $verificationHidden: Boolean,
) {
  addPost (
    postId: $postId,
    albumId: $albumId,
    text: $text,
    verificationHidden: $verificationHidden,
    mediaObjectUploads: [{
      mediaId: $mediaId,
      mediaType: $mediaType,
      takenInReal: $takenInReal,
      originalFormat: $originalFormat
    }],
    lifetime: $lifetime
  ) {
    postId
    postedAt
    postStatus
    expiresAt
    verificationHidden
    text
    textTaggedUsers {
      tag
      user {
        userId
        username
      }
    }
    album {
      albumId
    }
    mediaObjects {
      mediaId
      mediaStatus
      mediaType
      isVerified
      uploadUrl
      url
      height
      width
    }
    postedBy {
      userId
      postCount
      photoUrl
    }
  }
}`)

module.exports.addTwoMediaPost = gql(`mutation AddTwoMediaPost (
  $postId: ID!, $mediaId1: ID!, $mediaType1: MediaObjectType!, $mediaId2: ID!, $mediaType2: MediaObjectType!
) {
  addPost (
    postId: $postId,
    mediaObjectUploads: [{mediaId: $mediaId1, mediaType: $mediaType1}, {mediaId: $mediaId2, mediaType: $mediaType2}]
  ) {
    postId
    postedAt
    postStatus
    mediaObjects {
      mediaId
      mediaType
      mediaStatus
      url
      uploadUrl
    }
  }
}`)

module.exports.post = gql(`query Post ($postId: ID!, $onymouslyLikedByLimit: Int) {
  post (postId: $postId) {
    postId
    postStatus
    postedAt
    postedBy {
      userId
      postCount
    }
    expiresAt
    album {
      albumId
    }
    text
    textTaggedUsers {
      tag
      user {
        userId
        username
      }
    }
    mediaObjects {
      mediaId
      mediaStatus
      mediaType
      isVerified
      uploadUrl
      url
    }
    flagStatus
    likeStatus
    commentsDisabled
    commentCount
    comments {
      items {
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
          }
        }
      }
    }
    likesDisabled
    sharingDisabled
    verificationHidden
    onymousLikeCount
    anonymousLikeCount
    onymouslyLikedBy (limit: $onymouslyLikedByLimit) {
      items {
        userId
      }
    }
    viewedByCount
  }
}`)

module.exports.getPost = gql(`query GetPost ($postId: ID!) {
  getPost (postId: $postId) {
    postId
  }
}`)

module.exports.postViewedBy = gql(`query PostViewedBy ($postId: ID!) {
  post (postId: $postId) {
    postId
    viewedByCount
    viewedBy {
      items {
        userId
      }
    }
  }
}`)

module.exports.getPosts = gql(`query GetPosts ($userId: ID, $postStatus: PostStatus) {
  getPosts (userId: $userId, postStatus: $postStatus) {
    items {
      postId
      postedAt
      postStatus
      expiresAt
      text
      mediaObjects {
        mediaId
        mediaStatus
        url
        uploadUrl
      }
      postedBy {
        userId
        postCount
      }
    }
  }
}`)

module.exports.getMediaObjects = gql(`query GetMediaObjects ($userId: ID, $mediaStatus: MediaObjectStatus) {
  getMediaObjects (userId: $userId, mediaStatus: $mediaStatus) {
    items {
      mediaId
      mediaStatus
      uploadUrl
      height
      width
      url
      url64p
      url480p
      url1080p
      url4k
    }
  }
}`)

module.exports.editPost = gql(
  `mutation EditPost (
    $postId: ID!,
    $text: String,
    $commentsDisabled: Boolean,
    $likesDisabled: Boolean,
    $sharingDisabled: Boolean,
    $verificationHidden: Boolean,
  ) {
    editPost(
      postId: $postId,
      text: $text,
      commentsDisabled: $commentsDisabled,
      likesDisabled: $likesDisabled,
      sharingDisabled: $sharingDisabled,
      verificationHidden: $verificationHidden,
    ) {
      postId
      postStatus
      postedBy {
        userId
        postCount
      }
      text
      textTaggedUsers {
        tag
        user {
          userId
          username
        }
      }
      mediaObjects {
        mediaId
        mediaStatus
        url
      }
      commentsDisabled
      likesDisabled
      sharingDisabled
      verificationHidden
    }
  }`
)

module.exports.editPostAlbum = gql(
  `mutation EditPostAlbum ($postId: ID!, $albumId: ID) {
    editPostAlbum(postId: $postId, albumId: $albumId) {
      postId
      album {
        albumId
      }
    }
  }`
)

module.exports.editPostExpiresAt = gql(
  `mutation EditPostExpiresAt ($postId: ID!, $expiresAt: AWSDateTime) {
    editPostExpiresAt(postId: $postId, expiresAt: $expiresAt) {
      postId
      expiresAt
    }
  }`
)

module.exports.flagPost = gql(`mutation FlagPost ($postId: ID!) {
  flagPost(postId: $postId) {
    postId
    flagStatus
  }
}`)

module.exports.deletePost = gql(`mutation DeletePost ($postId: ID!) {
  deletePost(postId: $postId) {
    postId
    postStatus
    mediaObjects {
      mediaId
      mediaStatus
    }
  }
}`)

module.exports.archivePost = gql(`mutation ArchivePost ($postId: ID!) {
  archivePost(postId: $postId) {
    postId
    postStatus
    postedBy {
      userId
      postCount
    }
    mediaObjects {
      mediaId
      mediaStatus
      url
      url64p
      url480p
      url1080p
      url4k
      uploadUrl
    }
  }
}`)

module.exports.restoreArchivedPost = gql(`mutation RestoreArchivePost ($postId: ID!) {
  restoreArchivedPost(postId: $postId) {
    postId
    postStatus
    postedBy {
      userId
      postCount
    }
    mediaObjects {
      mediaId
      mediaStatus
      url
    }
  }
}`)

module.exports.followedUsers = gql(`query FollowedUsers ($userId: ID!, $followStatus: FollowStatus) {
  user (userId: $userId) {
    followedUsers (followStatus: $followStatus) {
      items {
        userId
        username
        privacyStatus
        fullName
        bio
        email
        phoneNumber
        followedStatus
        followerStatus
      }
    }
  }
}`)

module.exports.followerUsers = gql(`query FollowerUsers ($userId: ID!, $followStatus: FollowStatus) {
  user (userId: $userId) {
    followerUsers (followStatus: $followStatus) {
      items {
        userId
        followedStatus
        followerStatus
      }
    }
  }
}`)

module.exports.ourFollowedUsers = gql(`query OurFollowedUsers ($followStatus: FollowStatus) {
  self {
    followedUsers (followStatus: $followStatus) {
      items {
        userId
        username
        privacyStatus
        fullName
        bio
        email
        phoneNumber
        followedStatus
        followerStatus
      }
    }
  }
}`)

module.exports.ourFollowerUsers = gql(`query OurFollowerUsers ($followStatus: FollowStatus) {
  self {
    followerUsers (followStatus: $followStatus) {
      items {
        userId
        followedStatus
        followerStatus
      }
    }
  }
}`)

module.exports.getFollowedUsersWithStories = gql(`{
  getFollowedUsersWithStories {
    items {
      userId
    }
  }
}`)

module.exports.userStories = gql(`query UserStories ($userId: ID!) {
  user (userId: $userId) {
    stories {
      items {
        postId
        postedAt
        postedBy {
          userId
        }
        expiresAt
        text
        mediaObjects {
          mediaId
          mediaStatus
          url
        }
      }
    }
  }
}`)

module.exports.getFeed = gql(`query GetFeed ($limit: Int) {
  getFeed (limit: $limit) {
    items {
      postId
      postedBy {
        userId
      }
      text
      mediaObjects {
        mediaId
        url
        uploadUrl
      }
      onymousLikeCount
      anonymousLikeCount
    }
  }
}`)

module.exports.onymouslyLikePost = gql(`mutation OnymouslyLikePost ($postId: ID!) {
  onymouslyLikePost (postId: $postId) {
    postId
    likeStatus
    onymousLikeCount
    anonymousLikeCount
    onymouslyLikedBy {
      items {
        userId
      }
    }
  }
}`)

module.exports.anonymouslyLikePost = gql(`mutation AnonymouslyLikePost ($postId: ID!) {
  anonymouslyLikePost (postId: $postId) {
    postId
    likeStatus
    onymousLikeCount
    anonymousLikeCount
    onymouslyLikedBy {
      items {
        userId
      }
    }
  }
}`)

module.exports.dislikePost = gql(`mutation DislikePost ($postId: ID!) {
  dislikePost (postId: $postId) {
    postId
    likeStatus
    onymousLikeCount
    anonymousLikeCount
    onymouslyLikedBy {
      items {
        userId
      }
    }
  }
}`)

module.exports.reportPostViews = gql(`mutation ReportPostViews ($postIds: [ID!]!) {
  reportPostViews (postIds: $postIds)
}`)

module.exports.trendingUsers = gql(`query TrendingUsers ($limit: Int) {
  trendingUsers (limit: $limit) {
    items {
      userId
      blockerAt
      blockerStatus
    }
  }
}`)

module.exports.trendingPosts = gql(`query TrendingPosts ($limit: Int) {
  trendingPosts (limit: $limit) {
    items {
      postId
      postedBy {
        userId
        blockerAt
        blockerStatus
        privacyStatus
        followedStatus
      }
    }
  }
}`)


module.exports.addComment = gql(`mutation AddComment ($commentId: ID!, $postId: ID!, $text: String!) {
  addComment (commentId: $commentId, postId: $postId, text: $text) {
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
}`)


module.exports.deleteComment = gql(`mutation DeleteComment ($commentId: ID!) {
  deleteComment (commentId: $commentId) {
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
}`)


module.exports.addAlbum = gql(`mutation AddAlbum ($albumId: ID!, $name: String!, $description: String) {
  addAlbum (albumId: $albumId, name: $name, description: $description) {
    albumId
    ownedBy {
      userId
    }
    createdAt
    name
    description
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
}`)


module.exports.editAlbum = gql(`mutation EditAlbum ($albumId: ID!, $name: String, $description: String) {
  editAlbum (albumId: $albumId, name: $name, description: $description) {
    albumId
    ownedBy {
      userId
    }
    createdAt
    name
    description
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
}`)


module.exports.deleteAlbum = gql(`mutation DeleteAlbum ($albumId: ID!) {
  deleteAlbum (albumId: $albumId) {
    albumId
    ownedBy {
      userId
    }
    createdAt
    name
    description
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
}`)


module.exports.album = gql(`query Album ($albumId: ID!) {
  album (albumId: $albumId) {
    albumId
    ownedBy {
      userId
    }
    createdAt
    name
    description
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
}`)
