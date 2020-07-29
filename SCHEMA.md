# REAL Backend Dynamo Schema

As [recommended by AWS](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-general-nosql-design.html#bp-general-nosql-design-approach), REAL is following a single-table design. However, data is for the most part normalized because

- primary access is through graphql resolvers which map better to normalized data than de-normalized data
- normalized data allows for greater flexibility in access patterns, which is very useful with a brand-new product

## Table Schema

### Types

- Unless otherwise noted, all types are strings.
- Attributes that end with `At` are  (ex: `createdAt`) are of type [AWSDateTime](https://docs.aws.amazon.com/appsync/latest/devguide/scalars.html#appsync-defined-scalars), ie an ISO8601 datetime string, with timezone information that is always just 'Z'
- Attributes that end with `Count` are  (ex: `postCount`) are numbers (non-negative integers, actually).
- Attributes that end with `Id` are  (ex: `postId`) in general version 4 uuid's. An exception is `userId` which follows the format `{aws-region}:{uuid}`.

### Indexes

We have no local secondary indexes.

- The table's primary key is (`partitionKey`, `sortKey`).
- GSI-A1: (`gsiA1PartitionKey`, `gsiA1SortKey`) with keys and all attributes.
- GSI-A2: (`gsiA2PartitionKey`, `gsiA2SortKey`) with keys and all attributes.
- GSI-A3: (`gsiA3PartitionKey`, `gsiA3SortKey`) with keys and all attributes.
- GSI-K1: (`gsiK1PartitionKey`, `gsiK1SortKey`) with keys only.
- GSI-K2: (`gsiK2PartitionKey`, `gsiK2SortKey`) with keys only.
- GSI-K3: (`gsiK3PartitionKey`, `gsiK3SortKey:Number`) with keys only.

### Schema

| Table Partition Key `partitionKey` | Table Sort Key `sortKey` | Schema Version `schemaVersion` | Attributes | GSI-A1 Partition Key `gsiA1PartitionKey` | GSI-A1 Sort Key `gsiA1SortKey` | GSI-A2 Partition Key `gsiA2PartitionKey` | GSI-A2 Sort Key `gsiA2SortKey` | GSI-A3 Partition Key `gsiA3PartitionKey` | GSI-A3 Sort Key `gsiA3SortKey` | GSI-K1 Partition Key `gsiK1PartitionKey` | GSI-K1 Sort Key `gsiK1SortKey` | GSI-K2 Partition Key `gsiK2PartitionKey` | GSI-K2 Sort Key `gsiK2SortKey` | GSI-K3 Partition Key `gsiK3PartitionKey` | GSI-K3 Sort Key `gsiK3SortKey:Number` |
| - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| `user/{userId}` | `profile` | `10` | `userId`, `username`, `email`, `phoneNumber`, `fullName`, `bio`, `photoPostId`, `userStatus`, `privacyStatus`, `albumCount`, `chatMessagesCreationCount`, `chatMessagesDeletionCount`, `chatMessagesForcedDeletionCount`, `chatCount`, `chatsWithUnviewedMessagesCount`, `cardCount`, `commentCount`, `commentDeletedCount`, `commentForcedDeletionCount`, `followedCount`, `followerCount`, `followersRequestedCount`, `postCount`, `postArchivedCount`, `postDeletedCount`, `postForcedArchivingCount`, `lastManuallyReindexedAt`, `languageCode`, `themeCode`, `placeholderPhotoCode`, `signedUpAt`, `lastDisabedAt`, `acceptedEULAVersion`, `postViewedByCount`, `usernameLastValue`, `usernameLastChangedAt`, `followCountsHidden:Boolean`, `commentsDisabled:Boolean`, `likesDisabled:Boolean`, `sharingDisabled:Boolean`, `verificationHidden:Boolean` | `username/{username}` | `-` |
| `user/{userId}` | `follower/{userId}` | `1` | `followedAt`, `followStatus`, `followerUserId`, `followedUserId`  | `follower/{followerUserId}` | `{followStatus}/{followedAt}` | `followed/{followedUserId}` | `{followStatus}/{followedAt}` |
| `user/{userId}` | `follower/{userId}/firstStory` | `1` | `postId` | | | `follower/{followerUserId}/firstStory` | `{expiresAt}` |
| `user/{userId}` | `trending` | `0` | `lastDeflatedAt`, `createdAt` | | | | | | | | | | | `user/trending` | `{score}` |
| `block/{blockerUserId}/{blockedUserId}` | `-`| `0` | `blockerUserId`, `blockedUserId`, `blockedAt` | `block/{blockerUserId}` | `{blockedAt}` | `block/{blockedUserId}` | `{blockedAt}` |
| `post/{postId}` | `-` | `3` | `postId`, `postedAt`, `postedByUserId`, `postType`, `postStatus`, `albumId`, `originalPostId`, `expiresAt`, `text`, `textTags:[{tag, userId}]`, `checksum`, `isVerified:Boolean`, `viewedByCount`, `onymousLikeCount`, `anonymousLikeCount`, `flagCount`, `commentCount`, `commentsUnviewedCount`, `commentsDisabled:Boolean`, `likesDisabled:Boolean`, `sharingDisabled:Boolean`, `setAsUserPhoto:Boolean` | `post/{postedByUserId}` | `{postStatus}/{expiresAt}` | `post/{postedByUserId}` | `{postStatus}/{postedAt}` | `post/{postedByUserId}` | `{lastUnreadCommentAt}` | `post/{expiresAtDate}` | `{expiresAtTime}` | `postChecksum/{checksum}` | `{postedAt}` | `post/{albumId}` | `{albumRank:Number}` |
| `post/{postId}` | `feed/{userId}` | `3` | | `feed/{userId}` | `{postedAt}` | `feed/{userId}` | `{postedByUserId}` |
| `post/{postId}` | `flag/{userId}` | `0` | `createdAt` | | | | | | | `flag/{userId}` | `post` |
| `post/{postId}` | `image` | `0` | `takenInReal:Boolean`, `originalFormat`, `imageFormat`, `width:Number`, `height:Number`, `colors:[{r:Number, g:Number, b:Number}]` |
| `post/{postId}` | `like/{userId}` | `1` | `likedByUserId`, `likeStatus`, `likedAt`, `postId` | `like/{likedByUserId}` | `{likeStatus}/{likedAt}` | `like/{postId}` | `{likeStatus}/{likedAt}` | | | | | `like/{postedByUserId}` | `{likedByUserId}` |
| `post/{postId}` | `originalMetadata` | `0` | `originalMetadata` |
| `post/{postId}` | `trending` | `0` | `lastDeflatedAt`, `createdAt` | | | | | | | | | | | `post/trending` | `{score}` |
| `post/{postId}` | `view/{userId}` | `0` | `firstViewedAt`, `lastViewedAt`, `viewCount` | | | | | | | `post/{postId}` | `view/{firstViewedAt}` |
| `comment/{commentId}` | `-` | `1` | `commentId`, `postId`, `userId`, `commentedAt`, `text`, `textTags:[{tag, userId}]`, `flagCount` | `comment/{postId}` | `{commentedAt}` | `comment/{userId}` | `{commentedAt}` |
| `comment/{commentId}` | `flag/{userId}` | `0` | `createdAt` | | | | | | | `flag/{userId}` | `comment` |
| `album/{albumId}` | `-` | `0` | `albumId`, `ownedByUserId`, `name`, `description`, `createdAt`, `postCount`, `rankCount`, `postsLastUpdatedAt`, `artHash` | `album/{userId}` | `{createdAt}` | | | | | `album` | `{deleteAt}` |
| `card/{cardId}` | `-` | `0` | `title`, `subTitle`, `action`, `postId` | `user/{userId}` | `card/{createdAt}` | | | | | `card` | `{notifyUserAt}/{userId}` |
| `chat/{chatId}` | `-` | `0` | `chatId`, `chatType`, `name`, `createdByUserId`, `createdAt`, `lastMessageActivityAt`, `flagCount`, `messagesCount`, `userCount` | `chat/{userId1}/{userId2}` | `-` |
| `chat/{chatId}` | `flag/{userId}` | `0` | `createdAt` | | | | | | | `flag/{userId}` | `chat` |
| `chat/{chatId}` | `member/{userId}` | `1` | `messagesUnviewedCount` | | | | | | | `chat/{chatId}` | `member/{joinedAt}` | `member/{userId}` | `chat/{lastMessageActivityAt}` |
| `chat/{chatId}` | `view/{userId}` | `0` | `firstViewedAt`, `lastViewedAt`, `viewCount` | | | | | | | `chat/{chatId}` | `view/{firstViewedAt}` |
| `chatMessage/{messageId}` | `-` | `0` | `messageId`, `chatId`, `userId`, `createdAt`, `flagCount`, `lastEditedAt`, `text`, `textTags:[{tag, userId}]` | `chatMessage/{chatId}` | `{createdAt}` |
| `chatMessage/{messageId}` | `flag/{userId}` | `0` | `createdAt` | | | | | | | `flag/{userId}` | `chatMessage` |

### Notes

- `schemaVersion` is an number (non-negative integer, actually) attribute that is used for asynchronous data migrations.
- `username` is a human-readable string of their choosing
- `cardId` can be either a uuid or it can be a string of form `{userId}:{well-known-card-name}`
- `expiresAtDate` is of type [AWSDate](https://docs.aws.amazon.com/appsync/latest/devguide/scalars.html#appsync-defined-scalars) and `expiresAtTime` is of type [AWSTime](https://docs.aws.amazon.com/appsync/latest/devguide/scalars.html#appsync-defined-scalars). Neither have timezone information.
- keys that depend on optional attributes (ex: for posts, the GSI-A1 and GSI-K1 keys depend on `expiresAt`) will not be set if the optional attribute is not present
- `textTags` is a list of maps, each map having two keys `tag` and `userId` both with string values
- `colors` is a list of maps, each map having three numeric keys: `r`, `g`, and `b`
- `Post.albumRank` is -1 for non-COMPLETED posts in albums, and exclusively between -1 and 1 for COMPLETED posts in albums
- `Album.rankCount` is a count of the number of times rank of posts has been changed because of adding posts or editing existing post rank
- `Chat.gsiA1PartitionKey`:
  - is to be filled in if and only if `chatType == DIRECT`
  - `userId` and `userId2` in the field are the two users in the chat, their id's in alphanumeric sorted order
