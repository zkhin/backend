const gql = require('graphql-tag')

const fragments = require('./fragments.js')

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

// DEPRECATED
module.exports.addPostMediaUploads = gql`
  mutation AddPostMediaUploads (
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
      flagStatus
    }
  }
  ${fragments.comment}
  ${fragments.image}
  ${fragments.textTaggedUser}
`

module.exports.addPost = gql`
  mutation AddPost (
    $postId: ID!,
    $postType: PostType,
    $albumId: ID,
    $text: String,
    $imageData: String,
    $takenInReal: Boolean
    $imageFormat: ImageFormat,
    $originalFormat: String,
    $originalMetadata: String,
    $lifetime: String
    $commentsDisabled: Boolean,
    $likesDisabled: Boolean,
    $sharingDisabled: Boolean,
    $verificationHidden: Boolean,
    $setAsUserPhoto: Boolean,
  ) {
    addPost (
      postId: $postId,
      postType: $postType,
      albumId: $albumId,
      text: $text,
      imageInput: {
        takenInReal: $takenInReal,
        imageFormat: $imageFormat,
        originalFormat: $originalFormat,
        originalMetadata: $originalMetadata,
        imageData: $imageData,
      },
      lifetime: $lifetime,
      commentsDisabled: $commentsDisabled,
      likesDisabled: $likesDisabled,
      sharingDisabled: $sharingDisabled,
      verificationHidden: $verificationHidden,
      setAsUserPhoto: $setAsUserPhoto,
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
      viewedStatus
      text
      textTaggedUsers {
        ...TextTaggedUserFragment
      }
      image {
        ...ImageFragment
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
      flagStatus
    }
  }
  ${fragments.comment}
  ${fragments.image}
  ${fragments.textTaggedUser}
`

module.exports.addPostTwoMedia = gql`
  mutation AddPostTwoMedia ($postId: ID!, $mediaId1: ID!, $mediaId2: ID!) {
    addPost (postId: $postId, mediaObjectUploads: [{mediaId: $mediaId1}, {mediaId: $mediaId2}]) {
      postId
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
      postStatus
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

module.exports.createDirectChat = gql`
  mutation CreateDirectChat ($chatId: ID!, $userId: ID!, $messageId: ID! $messageText: String!) {
    createDirectChat (chatId: $chatId, userId: $userId, messageId: $messageId, messageText: $messageText) {
      ...ChatFragment
      messageCount
      messages {
        items {
          ...ChatMessageFragment
          viewedStatus
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
          viewedStatus
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
          viewedStatus
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
          viewedStatus
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
          viewedStatus
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
      viewedStatus
    }
  }
  ${fragments.chatMessage}
`

module.exports.editChatMessage = gql`
  mutation EditChatMessage ($messageId: ID!, $text: String!) {
    editChatMessage (messageId: $messageId, text: $text) {
      ...ChatMessageFragment
      viewedStatus
    }
  }
  ${fragments.chatMessage}
`

module.exports.deleteChatMessage = gql`
  mutation DeleteChatMessage ($messageId: ID!) {
    deleteChatMessage (messageId: $messageId) {
      ...ChatMessageFragment
      viewedStatus
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
      userId
    }
  }
`

module.exports.triggerPostNotification = gql`
  mutation TriggerPostNotification ($input: PostNotificationInput!) {
    triggerPostNotification (input: $input) {
      userId
    }
  }
`
