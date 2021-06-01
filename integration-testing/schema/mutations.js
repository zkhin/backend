import gql from 'graphql-tag'

import * as fragments from './fragments.js'

export const createAnonymousUser = gql`
  mutation CreateAnonymousUser {
    createAnonymousUser {
      AccessToken
      ExpiresIn
      TokenType
      RefreshToken
      IdToken
    }
  }
`

export const createCognitoOnlyUser = gql`
  mutation CreateCognitoOnlyUser($username: String!, $fullName: String) {
    createCognitoOnlyUser(username: $username, fullName: $fullName) {
      userId
      username
      fullName
      email
      phoneNumber
      signedUpAt
    }
  }
`

export const createAppleUser = gql`
  mutation CreateAppleUser($username: String!, $fullName: String, $appleIdToken: String!) {
    createAppleUser(username: $username, fullName: $fullName, appleIdToken: $appleIdToken) {
      userId
      username
      fullName
      email
    }
  }
`

export const createFacebookUser = gql`
  mutation CreateFacebookUser($username: String!, $fullName: String, $facebookAccessToken: String!) {
    createFacebookUser(username: $username, fullName: $fullName, facebookAccessToken: $facebookAccessToken) {
      userId
      username
      fullName
      email
    }
  }
`

export const createGoogleUser = gql`
  mutation CreateGoogleUser($username: String!, $fullName: String, $googleIdToken: String!) {
    createGoogleUser(username: $username, fullName: $fullName, googleIdToken: $googleIdToken) {
      userId
      username
      fullName
      email
    }
  }
`

export const setPassword = gql`
  mutation SetPassword($encryptedPassword: String!) {
    setUserPassword(encryptedPassword: $encryptedPassword) {
      userId
      username
    }
  }
`

export const setUsername = gql`
  mutation SetUsername($username: String!) {
    setUserDetails(username: $username) {
      userId
      username
    }
  }
`

export const setUserPrivacyStatus = gql`
  mutation SetUserPrivacyStatus($privacyStatus: PrivacyStatus!) {
    setUserDetails(privacyStatus: $privacyStatus) {
      userId
      privacyStatus
      followedsCount
      followersCount
    }
  }
`

export const setUserAcceptedEULAVersion = gql`
  mutation SetUserEULAVersion($version: String!) {
    setUserAcceptedEULAVersion(version: $version) {
      userId
      acceptedEULAVersion
    }
  }
`

export const setUserAPNSToken = gql`
  mutation SetUserAPNSToken($token: String!) {
    setUserAPNSToken(token: $token) {
      userId
    }
  }
`

export const setUserFollowCountsHidden = gql`
  mutation SetUserFollowCountsHidden($value: Boolean!) {
    setUserDetails(followCountsHidden: $value) {
      userId
      followCountsHidden
    }
  }
`

export const setUserViewCountsHidden = gql`
  mutation SetUserViewCountsHidden($value: Boolean!) {
    setUserDetails(viewCountsHidden: $value) {
      userId
      viewCountsHidden
    }
  }
`

export const setUserDetails = gql`
  mutation SetUserDetails(
    $bio: String
    $fullName: String
    $displayName: String
    $photoPostId: ID
    $username: String
    $dateOfBirth: AWSDate
    $gender: UserGender
    $location: LocationInput
    $height: Int
    $matchAgeRange: AgeRangeInput
    $matchGenders: [UserGender!]
    $matchLocationRadius: Int
    $matchHeightRange: HeightRangeInput
  ) {
    setUserDetails(
      bio: $bio
      fullName: $fullName
      displayName: $displayName
      photoPostId: $photoPostId
      username: $username
      dateOfBirth: $dateOfBirth
      gender: $gender
      location: $location
      height: $height
      matchAgeRange: $matchAgeRange
      matchGenders: $matchGenders
      matchLocationRadius: $matchLocationRadius
      matchHeightRange: $matchHeightRange
    ) {
      userId
      username
      bio
      fullName
      displayName
      photo {
        ...ImageFragment
      }
      dateOfBirth
      gender
      matchGenders
      matchLocationRadius
      datingStatus
    }
  }
  ${fragments.image}
`

export const setUserLanguageCode = gql`
  mutation SetUserLanguageCode($languageCode: String) {
    setUserDetails(languageCode: $languageCode) {
      userId
      languageCode
    }
  }
`

export const setThemeCode = gql`
  mutation SetThemeCode($themeCode: String!) {
    setThemeCode(themeCode: $themeCode) {
      userId
      themeCode
    }
  }
`

export const setUserMentalHealthSettings = gql`
  mutation SetUserMentalHealthSettings(
    $adsDisabled: Boolean
    $commentsDisabled: Boolean
    $likesDisabled: Boolean
    $sharingDisabled: Boolean
    $verificationHidden: Boolean
  ) {
    setUserDetails(
      adsDisabled: $adsDisabled
      commentsDisabled: $commentsDisabled
      likesDisabled: $likesDisabled
      sharingDisabled: $sharingDisabled
      verificationHidden: $verificationHidden
    ) {
      userId
      adsDisabled
      commentsDisabled
      likesDisabled
      sharingDisabled
      verificationHidden
    }
  }
`

export const setUserLocation = gql`
  mutation SetUserLocation($latitude: Float!, $longitude: Float!, $accuracy: Int) {
    setUserDetails(location: {latitude: $latitude, longitude: $longitude, accuracy: $accuracy}) {
      userId
      location {
        latitude
        longitude
        accuracy
      }
    }
  }
`

export const setUserAgeRange = gql`
  mutation SetUserAgeRange($min: Int, $max: Int) {
    setUserDetails(matchAgeRange: {min: $min, max: $max}) {
      userId
      matchAgeRange {
        min
        max
      }
    }
  }
`

export const setUserDatingStatus = gql`
  mutation SetUserDatingStatus($status: DatingStatus!) {
    setUserDatingStatus(status: $status) {
      userId
      datingStatus
    }
  }
`

export const startChangeUserEmail = gql`
  mutation StartChangeUserEmail($email: AWSEmail!) {
    startChangeUserEmail(email: $email) {
      userId
      username
      email
      phoneNumber
    }
  }
`

export const startChangeUserPhoneNumber = gql`
  mutation StartChangeUserPhoneNumber($phoneNumber: AWSPhone!) {
    startChangeUserPhoneNumber(phoneNumber: $phoneNumber) {
      userId
      username
      email
      phoneNumber
    }
  }
`

export const updateUserContactInfo = gql`
  mutation SetUserContactInfo($accessToken: String!) {
    updateUserContactInfo(authProvider: COGNITO, accessToken: $accessToken) {
      userId
      email
      phoneNumber
    }
  }
`

export const disableUser = gql`
  mutation DisableUser {
    disableUser {
      userId
      username
      userStatus
    }
  }
`

export const deleteUser = gql`
  mutation DeleteUser {
    deleteUser {
      userId
      username
      userStatus
    }
  }
`

export const grantUserSubscriptionBonus = gql`
  mutation GrantUserSubscriptionBonus($grantCode: SubscriptionGrantCode) {
    grantUserSubscriptionBonus(grantCode: $grantCode) {
      userId
      subscriptionLevel
      subscriptionExpiresAt
    }
  }
`

export const redeemPromotion = gql`
  mutation RedeemPromotion($code: String!) {
    redeemPromotion(code: $code) {
      userId
      subscriptionLevel
      subscriptionExpiresAt
    }
  }
`

export const addAppStoreReceipt = gql`
  mutation AddAppStoreReceipt($receiptData: String!) {
    addAppStoreReceipt(receiptData: $receiptData)
  }
`

export const resetUser = gql`
  mutation ResetUser($newUsername: String) {
    resetUser(newUsername: $newUsername) {
      userId
      username
      fullName
      userStatus
    }
  }
`

export const followUser = gql`
  mutation FollowUser($userId: ID!) {
    followUser(userId: $userId) {
      userId
      followedStatus
      followersCount
    }
  }
`

export const unfollowUser = gql`
  mutation UnfollowUser($userId: ID!) {
    unfollowUser(userId: $userId) {
      userId
      followedStatus
      followersCount
    }
  }
`

export const acceptFollowerUser = gql`
  mutation AcceptFollowerUser($userId: ID!) {
    acceptFollowerUser(userId: $userId) {
      userId
      followerStatus
      followedsCount
    }
  }
`

export const denyFollowerUser = gql`
  mutation DenyFollowerUser($userId: ID!) {
    denyFollowerUser(userId: $userId) {
      userId
      followerStatus
      followedsCount
    }
  }
`

export const blockUser = gql`
  mutation BlockUser($userId: ID!) {
    blockUser(userId: $userId) {
      userId
      blockedStatus
    }
  }
`

export const unblockUser = gql`
  mutation UnblockUser($userId: ID!) {
    unblockUser(userId: $userId) {
      userId
      blockedStatus
    }
  }
`

export const addPost = gql`
  mutation AddPost(
    $postId: ID!
    $postType: PostType
    $albumId: ID
    $text: String
    $imageData: String
    $takenInReal: Boolean
    $imageFormat: ImageFormat
    $originalFormat: String
    $originalMetadata: String
    $lifetime: String
    $commentsDisabled: Boolean
    $likesDisabled: Boolean
    $sharingDisabled: Boolean
    $verificationHidden: Boolean
    $setAsUserPhoto: Boolean
    $crop: CropInput
    $rotate: Int
    $keywords: [String!]
    $isAd: Boolean
    $adPayment: Float
    $adPaymentPeriod: String
  ) {
    addPost(
      postId: $postId
      postType: $postType
      albumId: $albumId
      text: $text
      imageInput: {
        takenInReal: $takenInReal
        imageFormat: $imageFormat
        originalFormat: $originalFormat
        originalMetadata: $originalMetadata
        imageData: $imageData
        crop: $crop
        rotate: $rotate
      }
      lifetime: $lifetime
      commentsDisabled: $commentsDisabled
      likesDisabled: $likesDisabled
      sharingDisabled: $sharingDisabled
      verificationHidden: $verificationHidden
      setAsUserPhoto: $setAsUserPhoto
      keywords: $keywords
      isAd: $isAd
      adPayment: $adPayment
      adPaymentPeriod: $adPaymentPeriod
    ) {
      postId
      postedAt
      postType
      postStatus
      expiresAt
      verificationHidden
      image {
        url
        url4k
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
      commentsCount
      comments {
        items {
          ...CommentFragment
        }
      }
      likesDisabled
      sharingDisabled
      verificationHidden
      flagStatus
      keywords
    }
  }
  ${fragments.comment}
  ${fragments.image}
  ${fragments.textTaggedUser}
`

export const editPost = gql`
  mutation EditPost(
    $postId: ID!
    $text: String
    $commentsDisabled: Boolean
    $likesDisabled: Boolean
    $sharingDisabled: Boolean
    $verificationHidden: Boolean
    $keywords: [String!]
  ) {
    editPost(
      postId: $postId
      text: $text
      commentsDisabled: $commentsDisabled
      likesDisabled: $likesDisabled
      sharingDisabled: $sharingDisabled
      verificationHidden: $verificationHidden
      keywords: $keywords
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
      keywords
    }
  }
  ${fragments.textTaggedUser}
`

export const editPostAlbum = gql`
  mutation EditPostAlbum($postId: ID!, $albumId: ID) {
    editPostAlbum(postId: $postId, albumId: $albumId) {
      postId
      album {
        albumId
      }
    }
  }
`

export const editPostAlbumOrder = gql`
  mutation EditPostAlbumOrder($postId: ID!, $precedingPostId: ID) {
    editPostAlbumOrder(postId: $postId, precedingPostId: $precedingPostId) {
      postId
      album {
        albumId
      }
    }
  }
`

export const editPostExpiresAt = gql`
  mutation EditPostExpiresAt($postId: ID!, $expiresAt: AWSDateTime) {
    editPostExpiresAt(postId: $postId, expiresAt: $expiresAt) {
      postId
      expiresAt
    }
  }
`

export const flagPost = gql`
  mutation FlagPost($postId: ID!) {
    flagPost(postId: $postId) {
      postId
      postStatus
      flagStatus
    }
  }
`

export const deletePost = gql`
  mutation DeletePost($postId: ID!) {
    deletePost(postId: $postId) {
      postId
      postStatus
    }
  }
`

export const archivePost = gql`
  mutation ArchivePost($postId: ID!) {
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

export const restoreArchivedPost = gql`
  mutation RestoreArchivePost($postId: ID!) {
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

export const approveAdPost = gql`
  mutation ApproveAdPost($postId: ID!) {
    approveAdPost(postId: $postId) {
      postId
      adStatus
    }
  }
`

export const onymouslyLikePost = gql`
  mutation OnymouslyLikePost($postId: ID!) {
    onymouslyLikePost(postId: $postId) {
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

export const anonymouslyLikePost = gql`
  mutation AnonymouslyLikePost($postId: ID!) {
    anonymouslyLikePost(postId: $postId) {
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

export const dislikePost = gql`
  mutation DislikePost($postId: ID!) {
    dislikePost(postId: $postId) {
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

export const reportPostViews = gql`
  mutation ReportPostViews($postIds: [ID!]!, $viewType: ViewType) {
    reportPostViews(postIds: $postIds, viewType: $viewType)
  }
`

export const reportScreenViews = gql`
  mutation ReportScreenViews($screens: [String!]!) {
    reportScreenViews(screens: $screens)
  }
`

export const deleteCard = gql`
  mutation DeleteCard($cardId: ID!) {
    deleteCard(cardId: $cardId) {
      ...CardFragment
    }
  }
  ${fragments.card}
`

export const addComment = gql`
  mutation AddComment($commentId: ID!, $postId: ID!, $text: String!) {
    addComment(commentId: $commentId, postId: $postId, text: $text) {
      ...CommentFragment
    }
  }
  ${fragments.comment}
`

export const deleteComment = gql`
  mutation DeleteComment($commentId: ID!) {
    deleteComment(commentId: $commentId) {
      ...CommentFragment
    }
  }
  ${fragments.comment}
`

export const flagComment = gql`
  mutation FlagComment($commentId: ID!) {
    flagComment(commentId: $commentId) {
      commentId
      flagStatus
    }
  }
`

export const addAlbum = gql`
  mutation AddAlbum($albumId: ID!, $name: String!, $description: String) {
    addAlbum(albumId: $albumId, name: $name, description: $description) {
      ...AlbumFragment
    }
  }
  ${fragments.album}
`

export const editAlbum = gql`
  mutation EditAlbum($albumId: ID!, $name: String, $description: String) {
    editAlbum(albumId: $albumId, name: $name, description: $description) {
      ...AlbumFragment
    }
  }
  ${fragments.album}
`

export const deleteAlbum = gql`
  mutation DeleteAlbum($albumId: ID!) {
    deleteAlbum(albumId: $albumId) {
      ...AlbumFragment
    }
  }
  ${fragments.album}
`

export const createDirectChat = gql`
  mutation CreateDirectChat($chatId: ID!, $userId: ID!, $messageId: ID!, $messageText: String!) {
    createDirectChat(chatId: $chatId, userId: $userId, messageId: $messageId, messageText: $messageText) {
      ...ChatFragment
      messages {
        items {
          ...ChatMessageFragment
          flagStatus
          viewedStatus
        }
      }
    }
  }
  ${fragments.chat}
  ${fragments.chatMessage}
`

export const createGroupChat = gql`
  mutation CreateGroupChat(
    $chatId: ID!
    $name: String
    $userIds: [ID!]!
    $messageId: ID!
    $messageText: String!
  ) {
    createGroupChat(
      chatId: $chatId
      name: $name
      userIds: $userIds
      messageId: $messageId
      messageText: $messageText
    ) {
      ...ChatFragment
      messages {
        items {
          ...ChatMessageFragment
          flagStatus
          viewedStatus
        }
      }
    }
  }
  ${fragments.chat}
  ${fragments.chatMessage}
`

export const editGroupChat = gql`
  mutation EditGroupChat($chatId: ID!, $name: String!) {
    editGroupChat(chatId: $chatId, name: $name) {
      ...ChatFragment
      messages {
        items {
          ...ChatMessageFragment
          flagStatus
          viewedStatus
        }
      }
    }
  }
  ${fragments.chat}
  ${fragments.chatMessage}
`

export const addToGroupChat = gql`
  mutation AddToGroupChat($chatId: ID!, $userIds: [ID!]!) {
    addToGroupChat(chatId: $chatId, userIds: $userIds) {
      ...ChatFragment
      messages {
        items {
          ...ChatMessageFragment
          flagStatus
          viewedStatus
        }
      }
    }
  }
  ${fragments.chat}
  ${fragments.chatMessage}
`

export const leaveGroupChat = gql`
  mutation LeaveGroupChat($chatId: ID!) {
    leaveGroupChat(chatId: $chatId) {
      ...ChatFragment
      messages {
        items {
          ...ChatMessageFragment
          flagStatus
          viewedStatus
        }
      }
    }
  }
  ${fragments.chat}
  ${fragments.chatMessage}
`

export const reportChatViews = gql`
  mutation ReportChatViews($chatIds: [ID!]!) {
    reportChatViews(chatIds: $chatIds)
  }
`

export const flagChat = gql`
  mutation FlagChat($chatId: ID!) {
    flagChat(chatId: $chatId) {
      chatId
      flagStatus
    }
  }
`

export const addChatMessage = gql`
  mutation AddChatMessage($chatId: ID!, $messageId: ID!, $text: String!) {
    addChatMessage(chatId: $chatId, messageId: $messageId, text: $text) {
      ...ChatMessageFragment
      flagStatus
      viewedStatus
    }
  }
  ${fragments.chatMessage}
`

export const editChatMessage = gql`
  mutation EditChatMessage($messageId: ID!, $text: String!) {
    editChatMessage(messageId: $messageId, text: $text) {
      ...ChatMessageFragment
      flagStatus
      viewedStatus
    }
  }
  ${fragments.chatMessage}
`

export const deleteChatMessage = gql`
  mutation DeleteChatMessage($messageId: ID!) {
    deleteChatMessage(messageId: $messageId) {
      ...ChatMessageFragment
      flagStatus
      viewedStatus
    }
  }
  ${fragments.chatMessage}
`

export const flagChatMessage = gql`
  mutation FlagChatMessage($messageId: ID!) {
    flagChatMessage(messageId: $messageId) {
      messageId
      flagStatus
    }
  }
`

export const rejectMatch = gql`
  mutation RejectMatch($userId: ID!) {
    rejectMatch(userId: $userId)
  }
`

export const approveMatch = gql`
  mutation ApproveMatch($userId: ID!) {
    approveMatch(userId: $userId)
  }
`

export const verifyIdentity = gql`
  mutation VerifyIdentity($frontsideImageData: String!) {
    verifyIdentity(frontsideImageData: $frontsideImageData) {
      userId
    }
  }
`

export const triggerNotification = gql`
  mutation TriggerNotification($input: NotificationInput!) {
    triggerNotification(input: $input) {
      userId
    }
  }
`

export const triggerCardNotification = gql`
  mutation TriggerCardNotification($input: CardNotificationInput!) {
    triggerCardNotification(input: $input) {
      userId
    }
  }
`

export const triggerChatMessageNotification = gql`
  mutation TriggerChatMessageNotification($input: ChatMessageNotificationInput!) {
    triggerChatMessageNotification(input: $input) {
      userId
    }
  }
`
