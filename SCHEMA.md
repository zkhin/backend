# REAL Backend Dynamo Schema

As [recommended by AWS](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-general-nosql-design.html#bp-general-nosql-design-approach), REAL is following a single-table design.

## Table Schema

  - Unless otherwise noted, all types are strings.
  - The table's primary key is (`partitionKey`, `sortKey`).
  - The item's `schemaVersion` is an integer attribute that is used for asynchronous data migrations.

| Table Partition Key `partitionKey` | Table Sort Key `sortKey` | Schema Version `schemaVersion` | Attributes | GSI-A1 Partition Key `gsiA1PartitionKey` | GSI-A1 Sort Key `gsiA1SortKey` | GSI-A2 Partition Key `gsiA2PartitionKey` | GSI-A2 Sort Key `gsiA2SortKey` | GSI-A3 Partition Key `gsiA3PartitionKey` | GSI-A3 Sort Key `gsiA3SortKey` | GSI-K1 Partition Key `gsiK1PartitionKey` | GSI-K1 Sort Key `gsiK1SortKey` | GSI-K2 Partition Key `gsiK2PartitionKey` | GSI-K2 Sort Key `gsiK2SortKey` | GSI-K3 Partition Key `gsiK3PartitionKey` | GSI-K3 Sort Key `gsiK3SortKey:Number` |
| - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| `user/{userId}` | `profile` | `9` | `userId`, `username`, `email`, `phoneNumber`, `fullName`, `bio`, `photoPostId`, `userStatus`, `privacyStatus`, `cardCount:Number`, `commentCount:Number`, `followedCount:Number`, `followerCount:Number`, `postCount:Number`, `postArchivedCount:Number`, `postDeletedCount:Number`, `postForcedArchivingCount:Number`, `albumCount:Number`, `chatCount:Number`, `chatsWithUnviewedMessagesCount:Number`, `lastManuallyReindexedAt`, `languageCode`, `themeCode`, `placeholderPhotoCode`, `signedUpAt`, `lastDisabedAt`, `acceptedEULAVersion`, `postViewedByCount:Number`, `usernameLastValue`, `usernameLastChangedAt`, `followCountsHidden:Boolean`, `commentsDisabled:Boolean`, `likesDisabled:Boolean`, `sharingDisabled:Boolean`, `verificationHidden:Boolean` | `username/{username}` | `-` |
| `user/{userId}` | `trending` | `0` | `lastDeflatedAt`, `createdAt` | | | | | | | | | | | `user/trending` | `{score}` |
| `following/{followerUserId}/{followedUserId}` | `-`| `1` | `followedAt`, `followStatus`, `followerUserId`, `followedUserId`  | `follower/{followerUserId}` | `{followStatus}/{followedAt}` | `followed/{followedUserId}` | `{followStatus}/{followedAt}` |
| `followedFirstStory/{followerUserId}/{postedByUserId}` | `-`| `1` | `postId`, `postedAt`, `postedByUserId`, `expiresAt` | `followedFirstStory/{followerUserId}` | `{expiresAt}` |
| `block/{blockerUserId}/{blockedUserId}` | `-`| `0` | `blockerUserId`, `blockedUserId`, `blockedAt` | `block/{blockerUserId}` | `{blockedAt}` | `block/{blockedUserId}` | `{blockedAt}` |
| `post/{postId}` | `-` | `3` | `postId`, `postedAt`, `postedByUserId`, `postType`, `postStatus`, `albumId`, `originalPostId`, `expiresAt`, `text`, `textTags:[{tag, userId}]`, `checksum`, `isVerified:Boolean`, `viewedByCount:Number`, `onymousLikeCount:Number`, `anonymousLikeCount:Number`, `flagCount:Number`, `commentCount:Number`, `commentsDisabled:Boolean`, `likesDisabled:Boolean`, `sharingDisabled:Boolean`, `setAsUserPhoto:Boolean` | `post/{postedByUserId}` | `{postStatus}/{expiresAt}` | `post/{postedByUserId}` | `{postStatus}/{postedAt}` | `post/{postedByUserId}` | `{lastNewCommentActivityAt}` | `post/{expiresAtDate}` | `{expiresAtTime}` | `postChecksum/{checksum}` | `{postedAt}` | `post/{albumId}` | `{albumRank:Number}` |
| `post/{postId}` | `flag/{userId}` | `0` | `createdAt` | | | | | | | `flag/{userId}` | `post` |
| `post/{postId}` | `image` | `0` | `takenInReal:Boolean`, `originalFormat`, `imageFormat`, `width:Number`, `height:Number`, `colors:[{r:Number, g:Number, b:Number}]` |
| `post/{postId}` | `originalMetadata` | `0` | `originalMetadata` |
| `post/{postId}` | `trending` | `0` | `lastDeflatedAt`, `createdAt` | | | | | | | | | | | `post/trending` | `{score}` |
| `post/{postId}` | `view/{userId}` | `0` | `firstViewedAt`, `lastViewedAt`, `viewCount:Number` | | | | | | | `post/{postId}` | `view/{firstViewedAt}` |
| `comment/{commentId}` | `-` | `1` | `commentId`, `postId`, `userId`, `commentedAt`, `text`, `textTags:[{tag, userId}]`, `flagCount:Number`, `viewedByCount:Number` | `comment/{postId}` | `{commentedAt}` | `comment/{userId}` | `{commentedAt}` |
| `comment/{commentId}` | `flag/{userId}` | `0` | `createdAt` | | | | | | | `flag/{userId}` | `comment` |
| `comment/{commentId}` | `view/{userId}` | `0` | `firstViewedAt`, `lastViewedAt`, `viewCount:Number` | | | | | | | `comment/{commentId}` | `view/{firstViewedAt}` |
| `feed/{userId}/{postId}` | `-` | `2` | `userId`, `postId`, `postedAt`, `postedByUserId`, | `feed/{userId}` | `{postedAt}` | | | | | | | `feed/{userId}/{postedByUserId}` | `{postedAt}` |
| `like/{likedByUserId}/{postId}` | `-` | `1` | `likedByUserId`, `likeStatus`, `likedAt`, `postId` | `like/{likedByUserId}` | `{likeStatus}/{likedAt}` | `like/{postId}` | `{likeStatus}/{likedAt}` | | | | | `like/{postedByUserId}` | `{likedByUserId}` |
| `album/{albumId}` | `-` | `0` | `albumId`, `ownedByUserId`, `name`, `description`, `createdAt`, `postCount:Number`, `rankCount:Number`, `postsLastUpdatedAt`, `artHash` | `album/{userId}` | `{createdAt}` |
| `card/{cardId}` | `-` | `0` | `title`, `subTitle`, `action` | `user/{userId}` | `card/{createdAt}` |
| `chat/{chatId}` | `-` | `0` | `chatId`, `chatType`, `name`, `createdByUserId`, `createdAt`, `lastMessageActivityAt`, `messageCount:Number`, `userCount:Number` | `chat/{userId1}/{userId2}` | `-` |
| `chat/{chatId}` | `member/{userId}` | `0` | `unviewedMessageCount:Number` | | | | | | | `chat/{chatId}` | `member/{joinedAt}` | `member/{userId}` | `chat/{lastMessageActivityAt}` |
| `chatMessage/{messageId}` | `-` | `0` | `messageId`, `chatId`, `userId`, `createdAt`, `lastEditedAt`, `text`, `textTags:[{tag, userId}]` | `chatMessage/{chatId}` | `{createdAt}` |
| `chatMessage/{messageId}` | `view/{userId}` | `0` | `firstViewedAt`, `lastViewedAt`, `viewCount:Number` | | | | | | | `chatMessage/{messageId}` | `view/{firstViewedAt}` |

Note that:

 - `userId` is both the cognito identity pool id for the user, and the cognito user pool 'username' (which isn't really a username at all)
 - `username` is a human-readable string of their choosing
 - other attributes that end with `Id` (ex: `postId`) are in general client-side-generated random uuids
 - `cardId` can be either a uuid or it can be a string of form `{userId}:{well-known-card-name}`
 - attributes that end with `At` are  (ex: `followedAt`) are of type [AWSDateTime](https://docs.aws.amazon.com/appsync/latest/devguide/scalars.html#appsync-defined-scalars), ie an ISO8601 datetime string, with timezone information that is always just 'Z'
 - `expiresAtDate` is of type [AWSDate](https://docs.aws.amazon.com/appsync/latest/devguide/scalars.html#appsync-defined-scalars) and `expiresAtTime` is of type [AWSTime](https://docs.aws.amazon.com/appsync/latest/devguide/scalars.html#appsync-defined-scalars). Neither have timezone information.
 - keys that depend on optional attributes (ex: for posts, the GSI-A1 and GSI-K1 keys depend on `expiresAt`) will not be set if the optional attribute is not present
 - `textTags` is a list of maps, each map having two keys `tag` and `userId` both with string values
 - `colors` is a list of maps, each map having three numeric keys: `r`, `g`, and `b`
 - `Post.albumRank` is -1 for non-COMPLETED posts in albums, and exclusively between -1 and 1 for COMPLETED posts in albums
 - `Album.rankCount` is a count of the number of times rank of posts has been changed because of adding posts or editing existing post rank
 - `Chat.gsiA1PartitionKey`:
    - is to be filled in if and only if `chatType == DIRECT`
    - `userId` and `userId2` in the field are the two users in the chat, their id's in alphanumeric sorted order

## Global Secondary Indexes

- GSI-A1: (`gsiA1PartitionKey`, `gsiA1SortKey`) with keys and all attributes.
- GSI-A2: (`gsiA2PartitionKey`, `gsiA2SortKey`) with keys and all attributes.
- GSI-A3: (`gsiA3PartitionKey`, `gsiA3SortKey`) with keys and all attributes.
- GSI-K1: (`gsiK1PartitionKey`, `gsiK1SortKey`) with keys only.
- GSI-K2: (`gsiK2PartitionKey`, `gsiK2SortKey`) with keys only.
- GSI-K3: (`gsiK3PartitionKey`, `gsiK3SortKey:Number`) with keys only.
