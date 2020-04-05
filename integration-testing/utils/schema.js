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

const fragments = require('./fragments.js')

module.exports.self = gql`
  query Self ($anonymouslyLikedPostsLimit: Int, $onymouslyLikedPostsLimit: Int) {
    self {
      userId
      ...SimpleUserFields
      photo {
        ...ImageFragment
      }
      feed {
        items {
          postId
        }
      }
      stories {
        items {
          postId
        }
      }
      posts {
        items {
          postId
        }
      }
      anonymouslyLikedPosts (limit: $anonymouslyLikedPostsLimit) {
        items {
          postId
          image {
            url
          }
        }
      }
      onymouslyLikedPosts (limit: $onymouslyLikedPostsLimit) {
        items {
          postId
          image {
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
      followedUsersWithStories {
        items {
          userId
          blockerStatus
          followedStatus
        }
      }
      blockedUsers {
        items {
          userId
          blockedStatus
        }
      }
      albumCount
      albums {
        items {
          ...AlbumFragment
        }
      }
      chatCount
      chats {
        items {
          ...ChatFragment
        }
      }
      directChat {
        ...ChatFragment
      }
    }
  }
  ${fragments.album}
  ${fragments.chat}
  ${fragments.image}
  ${fragments.simpleUserFields}
`

module.exports.user = gql`
  query User ($userId: ID!) {
    user (userId: $userId) {
      userId
      ...SimpleUserFields
      photo {
        ...ImageFragment
      }
      feed {
        items {
          postId
        }
      }
      stories {
        items {
          postId
        }
      }
      posts {
        items {
          postId
        }
      }
      anonymouslyLikedPosts {
        items {
          postId
          image {
            url
          }
        }
      }
      onymouslyLikedPosts {
        items {
          postId
          image {
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
      followedUsersWithStories {
        items {
          userId
        }
      }
      blockedUsers {
        items {
          userId
          blockedStatus
        }
      }
      albumCount
      albums {
        items {
          ...AlbumFragment
        }
      }
      chatCount
      chats {
        items {
          ...ChatFragment
        }
      }
      directChat {
        ...ChatFragment
      }
    }
  }
  ${fragments.album}
  ${fragments.chat}
  ${fragments.image}
  ${fragments.simpleUserFields}
`

module.exports.createCognitoOnlyUser = gql`
  mutation CreateCognitoOnlyUser ($username: String!, $fullName: String) {
    createCognitoOnlyUser (username: $username, fullName: $fullName) {
      userId
      username
      fullName
      email
      phoneNumber
      signedUpAt
    }
  }
`

module.exports.createGoogleUser = gql`
  mutation CreateGoogleUser ($username: String!, $fullName: String, $googleIdToken: String!) {
    createGoogleUser (username: $username, fullName: $fullName, googleIdToken: $googleIdToken) {
      userId
      username
      fullName
      email
    }
  }
`

module.exports.createFacebookUser = gql`
  mutation CreateFacebookUser ($username: String!, $fullName: String, $facebookAccessToken: String!) {
    createFacebookUser (username: $username, fullName: $fullName, facebookAccessToken: $facebookAccessToken) {
      userId
      username
      fullName
      email
    }
  }
`

module.exports.searchUsers = gql`
  query SearchUsers ($searchToken: String!) {
    searchUsers (searchToken: $searchToken) {
      items {
        userId
        username
        fullName
        photo {
          url
        }
      }
    }
  }
`

module.exports.setUsername = gql`
  mutation SetUsername ($username: String!) {
    setUserDetails (username: $username) {
      userId
      username
    }
  }
`

module.exports.setUserPrivacyStatus = gql`
  mutation SetUserPrivacyStatus ($privacyStatus: PrivacyStatus!) {
    setUserDetails (privacyStatus: $privacyStatus) {
      userId
      privacyStatus
      followedCount
      followerCount
    }
  }
`

module.exports.setUserAcceptedEULAVersion = gql`
  mutation SetUserEULAVersion ($version: String!) {
    setUserAcceptedEULAVersion (version: $version) {
      userId
      acceptedEULAVersion
    }
  }
`

module.exports.setUserFollowCountsHidden = gql`
  mutation SetUserFollowCountsHidden ($value: Boolean!) {
    setUserDetails (followCountsHidden: $value) {
      userId
      followCountsHidden
    }
  }
`

module.exports.setUserViewCountsHidden = gql`
  mutation SetUserViewCountsHidden ($value: Boolean!) {
    setUserDetails (viewCountsHidden: $value) {
      userId
      viewCountsHidden
    }
  }
`

module.exports.setUserDetails = gql`
  mutation SetUserDetails ($bio: String, $fullName: String, $photoPostId: ID) {
    setUserDetails (bio: $bio, fullName: $fullName, photoPostId: $photoPostId) {
      userId
      bio
      fullName
      photo {
        ...ImageFragment
      }
    }
  }
  ${fragments.image}
`

module.exports.setUserLanguageCode = gql`
  mutation SetUserLanguageCode ($languageCode: String) {
    setUserDetails (languageCode: $languageCode) {
      userId
      languageCode
    }
  }
`

module.exports.setUserThemeCode = gql`
  mutation SetUserThemeCode ($themeCode: String) {
    setUserDetails (themeCode: $themeCode) {
      userId
      themeCode
    }
  }
`

module.exports.setUserMentalHealthSettings = gql`
  mutation SetUserCommentsDisabled (
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
  }
`

module.exports.updateUserContactInfo = gql`
  mutation SetUserContactInfo ($accessToken: String!) {
    updateUserContactInfo (authProvider: COGNITO, accessToken: $accessToken) {
      userId
      email
      phoneNumber
    }
  }
`

module.exports.resetUser = gql`
  mutation ResetUser ($newUsername: String) {
    resetUser (newUsername: $newUsername) {
      userId
      username
      fullName
    }
  }
`

module.exports.followUser = gql`
  mutation FollowUser ($userId: ID!) {
    followUser (userId: $userId) {
      userId
      followedStatus
      followerCount
    }
  }
`

module.exports.unfollowUser = gql`
  mutation UnfollowUser ($userId: ID!) {
    unfollowUser (userId: $userId) {
      userId
      followedStatus
      followerCount
    }
  }
`

module.exports.acceptFollowerUser = gql`
  mutation AcceptFollowerUser ($userId: ID!) {
    acceptFollowerUser (userId: $userId) {
      userId
      followerStatus
      followedCount
    }
  }
`

module.exports.denyFollowerUser = gql`
  mutation DenyFollowerUser ($userId: ID!) {
    denyFollowerUser (userId: $userId) {
      userId
      followerStatus
      followedCount
    }
  }
`

module.exports.blockUser = gql`
  mutation BlockUser ($userId: ID!) {
    blockUser (userId: $userId) {
      userId
      blockedStatus
    }
  }
`

module.exports.unblockUser = gql`
  mutation UnblockUser ($userId: ID!) {
    unblockUser (userId: $userId) {
      userId
      blockedStatus
    }
  }
`

module.exports.addPost = gql`
  mutation AddPost (
    $postId: ID!,
    $postType: PostType,
    $mediaId: ID!,
    $imageData: String,
    $albumId: ID,
    $text: String,
    $lifetime: String
    $takenInReal: Boolean
    $originalFormat: String,
    $commentsDisabled: Boolean,
    $likesDisabled: Boolean,
    $sharingDisabled: Boolean,
    $verificationHidden: Boolean,
  ) {
    addPost (
      postId: $postId,
      postType: $postType,
      albumId: $albumId,
      text: $text,
      lifetime: $lifetime,
      commentsDisabled: $commentsDisabled,
      likesDisabled: $likesDisabled,
      sharingDisabled: $sharingDisabled,
      verificationHidden: $verificationHidden,
      mediaObjectUploads: [{
        mediaId: $mediaId,
        takenInReal: $takenInReal,
        originalFormat: $originalFormat,
        imageData: $imageData,
      }],
    ) {
      postId
      postedAt
      postType
      postStatus
      expiresAt
      verificationHidden
      text
      textTaggedUsers {
        ...TextTaggedUserFragment
      }
      image {
        ...ImageFragment
      }
      imageUploadUrl
      isVerified
      viewedStatus
      album {
        albumId
      }
      originalPost {
        postId
      }
      postedBy {
        userId
        postCount
        blockerStatus
        followedStatus
      }
      commentsDisabled
      commentCount
      comments {
        items {
          ...CommentFragment
        }
      }
      likesDisabled
      sharingDisabled
      verificationHidden
      hasNewCommentActivity
    }
  }
  ${fragments.comment}
  ${fragments.image}
  ${fragments.textTaggedUser}
`

// Note: this will be merged with module.exports.addPost when mediaObjectUploads are dropped
module.exports.addPostNoMedia = gql`
  mutation AddPost (
    $postId: ID!,
    $postType: PostType,
    $albumId: ID,
    $text: String,
    $lifetime: String
    $commentsDisabled: Boolean,
    $likesDisabled: Boolean,
    $sharingDisabled: Boolean,
    $verificationHidden: Boolean,
  ) {
    addPost (
      postId: $postId,
      postType: $postType,
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
      postType
      postStatus
      expiresAt
      verificationHidden
      image {
        url
      }
      imageUploadUrl
      videoUploadUrl
      isVerified
      text
      textTaggedUsers {
        ...TextTaggedUserFragment
      }
      album {
        albumId
      }
      originalPost {
        postId
      }
      postedBy {
        userId
        postCount
        blockerStatus
        followedStatus
      }
      commentsDisabled
      commentCount
      comments {
        items {
          ...CommentFragment
        }
      }
      likesDisabled
      sharingDisabled
      verificationHidden
      hasNewCommentActivity
    }
  }
  ${fragments.comment}
  ${fragments.textTaggedUser}
`

module.exports.addPostTwoMedia = gql`
  mutation AddPostTwoMedia ($postId: ID!, $mediaId1: ID!, $mediaId2: ID!) {
    addPost (postId: $postId, mediaObjectUploads: [{mediaId: $mediaId1}, {mediaId: $mediaId2}]) {
      postId
    }
  }
`

module.exports.post = gql`
  query Post ($postId: ID!, $onymouslyLikedByLimit: Int, $commentsReverse: Boolean) {
    post (postId: $postId) {
      postId
      postType
      postStatus
      postedAt
      postedBy {
        userId
        postCount
        blockerStatus
        followedStatus
        postHasNewCommentActivity
      }
      expiresAt
      album {
        albumId
      }
      originalPost {
        postId
      }
      text
      textTaggedUsers {
        ...TextTaggedUserFragment
      }
      image {
        ...ImageFragment
      }
      imageUploadUrl
      video {
        ...VideoFragment
      }
      videoUploadUrl
      isVerified
      flagStatus
      likeStatus
      viewedStatus
      commentsDisabled
      commentCount
      comments (reverse: $commentsReverse) {
        items {
          ...CommentFragment
        }
      }
      likesDisabled
      sharingDisabled
      verificationHidden
      hasNewCommentActivity
      onymousLikeCount
      anonymousLikeCount
      onymouslyLikedBy (limit: $onymouslyLikedByLimit) {
        items {
          userId
        }
      }
      viewedByCount
      viewedBy {
        items {
          userId
        }
      }
    }
  }
  ${fragments.comment}
  ${fragments.image}
  ${fragments.textTaggedUser}
  ${fragments.video}
`

module.exports.getPost = gql`
  query GetPost ($postId: ID!) {
    getPost (postId: $postId) {
      postId
    }
  }
`

module.exports.userPosts = gql`
  query UserPosts ($userId: ID!, $postStatus: PostStatus, $postType: PostType) {
    user (userId: $userId) {
      posts (postStatus: $postStatus, postType: $postType) {
        items {
          postId
          postedAt
          postType
          postStatus
          expiresAt
          text
          image {
            url
          }
          postedBy {
            userId
            postCount
            blockerStatus
            followedStatus
          }
        }
      }
    }
  }
`

module.exports.editPost = gql`
  mutation EditPost (
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
        blockerStatus
        followedStatus
      }
      text
      textTaggedUsers {
        ...TextTaggedUserFragment
      }
      image {
        url
      }
      commentsDisabled
      likesDisabled
      sharingDisabled
      verificationHidden
    }
  }
  ${fragments.textTaggedUser}
`

module.exports.editPostAlbum = gql`
  mutation EditPostAlbum ($postId: ID!, $albumId: ID) {
    editPostAlbum(postId: $postId, albumId: $albumId) {
      postId
      album {
        albumId
      }
    }
  }
`

module.exports.editPostAlbumOrder = gql`
  mutation EditPostAlbumOrder ($postId: ID!, $precedingPostId: ID) {
    editPostAlbumOrder(postId: $postId, precedingPostId: $precedingPostId) {
      postId
      album {
        albumId
      }
    }
  }
`

module.exports.editPostExpiresAt = gql`
  mutation EditPostExpiresAt ($postId: ID!, $expiresAt: AWSDateTime) {
    editPostExpiresAt(postId: $postId, expiresAt: $expiresAt) {
      postId
      expiresAt
    }
  }
`

module.exports.flagPost = gql`
  mutation FlagPost ($postId: ID!) {
    flagPost(postId: $postId) {
      postId
      flagStatus
    }
  }
`

module.exports.deletePost = gql`
  mutation DeletePost ($postId: ID!) {
    deletePost(postId: $postId) {
      postId
      postStatus
    }
  }
`

module.exports.archivePost = gql`
  mutation ArchivePost ($postId: ID!) {
    archivePost(postId: $postId) {
      postId
      postStatus
      postedBy {
        userId
        postCount
        blockerStatus
        followedStatus
      }
      image {
        url
      }
      imageUploadUrl
      videoUploadUrl
    }
  }
`

module.exports.restoreArchivedPost = gql`
  mutation RestoreArchivePost ($postId: ID!) {
    restoreArchivedPost(postId: $postId) {
      postId
      postStatus
      postedBy {
        userId
        postCount
        blockerStatus
        followedStatus
      }
      image {
        url
      }
    }
  }
`

module.exports.followedUsers = gql`
  query FollowedUsers ($userId: ID!, $followStatus: FollowStatus) {
    user (userId: $userId) {
      followedUsers (followStatus: $followStatus) {
        items {
          userId
          followedStatus
          followerStatus
        }
      }
    }
  }
`

module.exports.followerUsers = gql`
  query FollowerUsers ($userId: ID!, $followStatus: FollowStatus) {
    user (userId: $userId) {
      followerUsers (followStatus: $followStatus) {
        items {
          userId
          followedStatus
          followerStatus
        }
      }
    }
  }
`

module.exports.ourFollowedUsers = gql`
  query OurFollowedUsers ($followStatus: FollowStatus) {
    self {
      followedUsers (followStatus: $followStatus) {
        items {
          userId
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
  }
`

module.exports.ourFollowerUsers = gql`
  query OurFollowerUsers ($followStatus: FollowStatus) {
    self {
      followerUsers (followStatus: $followStatus) {
        items {
          userId
          followedStatus
          followerStatus
        }
      }
    }
  }
`

module.exports.userStories = gql`
  query UserStories ($userId: ID!) {
    user (userId: $userId) {
      stories {
        items {
          postId
          postedAt
          postedBy {
            userId
            blockerStatus
            followedStatus
          }
          expiresAt
          text
          image {
            url
          }
        }
      }
    }
  }
`

module.exports.selfFeed = gql`
  query SelfFeed ($limit: Int) {
    self {
      feed (limit: $limit) {
        items {
          postId
          postType
          postedBy {
            userId
            blockerStatus
            followedStatus
          }
          text
          image {
            url
          }
          imageUploadUrl
          videoUploadUrl
          onymousLikeCount
          anonymousLikeCount
        }
      }
    }
  }
`

module.exports.onymouslyLikePost = gql`
  mutation OnymouslyLikePost ($postId: ID!) {
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
  }
`

module.exports.anonymouslyLikePost = gql`
  mutation AnonymouslyLikePost ($postId: ID!) {
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
  }
`

module.exports.dislikePost = gql`
  mutation DislikePost ($postId: ID!) {
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
  }
`

module.exports.reportPostViews = gql`
  mutation ReportPostViews ($postIds: [ID!]!) {
    reportPostViews (postIds: $postIds)
  }
`

module.exports.trendingUsers = gql`
  query TrendingUsers ($limit: Int) {
    trendingUsers (limit: $limit) {
      items {
        userId
        blockerStatus
      }
    }
  }
`

module.exports.trendingPosts = gql`
  query TrendingPosts ($limit: Int) {
    trendingPosts (limit: $limit) {
      items {
        postId
        postedBy {
          userId
          privacyStatus
          blockerStatus
          followedStatus
        }
      }
    }
  }
`

module.exports.addComment = gql`
  mutation AddComment ($commentId: ID!, $postId: ID!, $text: String!) {
    addComment (commentId: $commentId, postId: $postId, text: $text) {
      ...CommentFragment
    }
  }
  ${fragments.comment}
`

module.exports.deleteComment = gql`
  mutation DeleteComment ($commentId: ID!) {
    deleteComment (commentId: $commentId) {
      ...CommentFragment
    }
  }
  ${fragments.comment}
`

module.exports.reportCommentViews = gql`
  mutation ReportCommentViews ($commentIds: [ID!]!) {
    reportCommentViews (commentIds: $commentIds)
  }
`

module.exports.addAlbum = gql`
  mutation AddAlbum ($albumId: ID!, $name: String!, $description: String) {
    addAlbum (albumId: $albumId, name: $name, description: $description) {
      ...AlbumFragment
    }
  }
  ${fragments.album}
`

module.exports.editAlbum = gql`
  mutation EditAlbum ($albumId: ID!, $name: String, $description: String) {
    editAlbum (albumId: $albumId, name: $name, description: $description) {
      ...AlbumFragment
    }
  }
  ${fragments.album}
`

module.exports.deleteAlbum = gql`
  mutation DeleteAlbum ($albumId: ID!) {
    deleteAlbum (albumId: $albumId) {
      ...AlbumFragment
    }
  }
  ${fragments.album}
`

module.exports.album = gql`
  query Album ($albumId: ID!) {
    album (albumId: $albumId) {
      ...AlbumFragment
    }
  }
  ${fragments.album}
`

module.exports.chat = gql`
  query Chat ($chatId: ID!, $reverse: Boolean) {
    chat (chatId: $chatId) {
      ...ChatFragment
      messageCount
      messages (reverse: $reverse) {
        items {
          ...ChatMessageFragment
        }
      }
    }
  }
  ${fragments.chat}
  ${fragments.chatMessage}
`

module.exports.createDirectChat = gql`
  mutation CreateDirectChat ($chatId: ID!, $userId: ID!, $messageId: ID! $messageText: String!) {
    createDirectChat (chatId: $chatId, userId: $userId, messageId: $messageId, messageText: $messageText) {
      ...ChatFragment
      messageCount
      messages {
        items {
          ...ChatMessageFragment
        }
      }
    }
  }
  ${fragments.chat}
  ${fragments.chatMessage}
`

module.exports.createGroupChat = gql`
  mutation CreateGroupChat ($chatId: ID!, $name: String, $userIds: [ID!]!, $messageId: ID! $messageText: String!) {
    createGroupChat (
      chatId: $chatId, name: $name, userIds: $userIds, messageId: $messageId, messageText: $messageText,
    ) {
      ...ChatFragment
      messageCount
      messages {
        items {
          ...ChatMessageFragment
        }
      }
    }
  }
  ${fragments.chat}
  ${fragments.chatMessage}
`

module.exports.editGroupChat = gql`
  mutation EditGroupChat ($chatId: ID!, $name: String!) {
    editGroupChat (chatId: $chatId, name: $name) {
      ...ChatFragment
      messageCount
      messages {
        items {
          ...ChatMessageFragment
        }
      }
    }
  }
  ${fragments.chat}
  ${fragments.chatMessage}
`

module.exports.addToGroupChat = gql`
  mutation AddToGroupChat ($chatId: ID!, $userIds: [ID!]!) {
    addToGroupChat (chatId: $chatId, userIds: $userIds) {
      ...ChatFragment
      messageCount
      messages {
        items {
          ...ChatMessageFragment
        }
      }
    }
  }
  ${fragments.chat}
  ${fragments.chatMessage}
`

module.exports.leaveGroupChat = gql`
  mutation LeaveGroupChat ($chatId: ID!) {
    leaveGroupChat (chatId: $chatId) {
      ...ChatFragment
      messageCount
      messages {
        items {
          ...ChatMessageFragment
        }
      }
    }
  }
  ${fragments.chat}
  ${fragments.chatMessage}
`

module.exports.addChatMessage = gql`
  mutation AddChatMessage ($chatId: ID!, $messageId: ID!, $text: String!) {
    addChatMessage (chatId: $chatId, messageId: $messageId, text: $text) {
      ...ChatMessageFragment
    }
  }
  ${fragments.chatMessage}
`

module.exports.editChatMessage = gql`
  mutation EditChatMessage ($messageId: ID!, $text: String!) {
    editChatMessage (messageId: $messageId, text: $text) {
      ...ChatMessageFragment
    }
  }
  ${fragments.chatMessage}
`

module.exports.deleteChatMessage = gql`
  mutation DeleteChatMessage ($messageId: ID!) {
    deleteChatMessage (messageId: $messageId) {
      ...ChatMessageFragment
    }
  }
  ${fragments.chatMessage}
`

module.exports.reportChatMessageViews = gql`
  mutation ReportChatMessageViews ($messageIds: [ID!]!) {
    reportChatMessageViews (messageIds: $messageIds)
  }
`

module.exports.triggerChatMessageNotification = gql`
  mutation TriggerChatMessageNotification ($input: ChatMessageNotificationInput!) {
    triggerChatMessageNotification (input: $input) {
      ...ChatMessageNotificationFragment
    }
  }
  ${fragments.chatMessageNotification}
`

module.exports.onChatMessageNotification = gql`
  subscription OnChatMessageNotification ($userId: ID!) {
    onChatMessageNotification (userId: $userId) {
      ...ChatMessageNotificationFragment
    }
  }
  ${fragments.chatMessageNotification}
`
