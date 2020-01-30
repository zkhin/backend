# REAL Backend

## Overview

[serverless](https://serverless.com) is used to manage this project.

The backend is organized as a series of cloudformation stacks to speed up the standard deploy and to help protect stateful resources. The stacks so far are:

- `real-main`
- `real-lambda-layers`
- `real-cloudfront`

## Getting started

Installed on your system you will need `npm`, `nodejs12`, `serverless`, `python3.7`, `pipenv`, `docker`.

In each of the stack root directories, run `npm install` to install serverless and required plugins.

## Deployment

To deploy each serverless stack, run `sls deploy` in that stack's root directory. Note that:

- unless given the [`--aws-profile`](https://serverless.com/framework/docs/providers/aws/guide/credentials/#using-aws-profiles) option, serverless will use the default AWS credentials to do the deployment (usually stored in `~/.aws/credentials`).
- serverless expects the AWS credentials to have `AdministratorAccess` policy attached.

### A brand-new deployment

Before first deployment in a new AWS account, there is some one-time set-up to do with [SES](https://console.aws.amazon.com/ses/home) so it can send transactional emails from Cognito:
- add and verify the domain `real.app`
- add and verify the email address `no-reply@real.app`.
- optionally set up spf, dkim, dmarc and a MAIL FROM domain of `mail.real.app`

Because there are resource dependencies between some of the stacks, they must be deployed in this order.

- `real-lambda-layers`
- `real-main`
- `real-cloudfront`
- `real-main` again

A CloudFront Key Pair will also need to be generated and stored in the AWS Secrets Manager. To do so, one must login to the AWS Console using the account's *root* credentials. See [Setting up CloudFront Signed URLs](#setting-up-cloudfront-signed-urls) for details.

Google needs to be configured as an [IAM OIDC Provider](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html) before `real-main` can be deployed. Step-by-step instructions are available [here](https://medium.com/fullstack-with-react-native-aws-serverless-and/set-up-openid-connect-oidc-provider-in-aws-91d498f3c9f7).

### Updates to an existing deployment

In general, only stacks that have been changed since the last deployment need to be redeployed.

However, if a stack changed naming or versioning of a resource that another stack depends on, then the dependent stack needs to be redeployed as well. For example:

- when the `real-lambda-layers` stack is redeployed with new python packages, its lambda layer version number is incremented
- old versions of the `real-lambda-layers` are retained to allow rolling back a deployment of a dependent stack (ie: `real-main`) if necessary. Old versions of the layer should be deleted manually via the AWS Console once all stacks using the layer have been upgraded to use the new version.
- in order for the `real-main` lambda handlers to the latest version of that lambda layer, `real-main` must be redeployed as well

## External-facing API's, resources

### AppSync graphql endpoint

- Browse the [graphql schema](./real-main/schema.graphql).
- Endpoint url is provided by CloudFormation output `real-<stage>-main.GraphQlApiUrl`

### Cognito User Pool

- Allows authentication of new and existing users with email/phone and password
- User pool client id is provided by CloudFormation output `real-<stage>-main.CognitoFrontendUserPoolClientId`
- If SES is still in sandbox mode for the AWS Account (it is if you haven't [moved it out of the sandbox](https://docs.aws.amazon.com/ses/latest/DeveloperGuide/request-production-access.html)) then Cognito will only be able to send emails to addresses that have been verified either in IAM or in SES.

## Running the tests

### Integration tets

Please see the [Integation Testing README](./integration-testing/README.md)

### Unit tests

The unit tests of the python lambda handlers in the primary stack use [pytest](http://doc.pytest.org/en/latest/). To run them:

```sh
cd real-main
pipenv shell
pytest app_tests/
```

## Development

### The serverless stacks

#### `real-main`

This is the primary stack, it holds everything not explicitly relegated to one of the other stacks.

Most development takes place here. To initialize the development environment, run `pipenv install --dev` in the stack root directory.

#### `real-lambda-layers`

Holds the [lambda layers](https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html). The python packages which the lambda handlers in the primary stack depend on are stored in a layer. This reduces the size of the deployment package of the primary stack from several megabytes to several kilobytes, making deploys of the primary stack much faster.

#### `real-cloudfront`

Holds:

- CloudFront CDN for the main 'uploads' bucket
- Lambda@Edge handlers for that CloudFront instance

The Lambda@Edge handlers need to be broken into a separate stack because:

- they are included in every deploy regardless of whether they have changed or not
- re-deploying them takes ~20 minutes

CloudFront is included because:

- changes to the CloudFront config, while somewhat uncommon, also trigger a ~20 minute deploy
- separating the CloudFront config and the Lambda@Edge handlers into separate stacks isn't supported by the [cloudfront-lambda-edge serverless plugin](https://github.com/silvermine/serverless-plugin-cloudfront-lambda-edge/)

### Adding new python dependencies

Note that new python packages dependencies for the lambda handlers in the primary `real-main` stack should be installed in two places:

- in the primary `real-main` stack as a dev dependency: `pipenv install --dev <package name>`
- in the `real-main-lambda-layers` stack as a runtime dependency: `pipenv install <package name>`

After adding a new dependency, the `real-main-lambda-layers` stack should be re-deployed first, followed by the `real-main` stack.

### Setting up CloudFront Signed URLs

After a deploy to a new account, a CloudFront key pair needs to be manually generated and stored in the AWS secrets manager.

- a new CloudFront key pair can be generated in the [your security credentials](https://console.aws.amazon.com/iam/home#/security_credentials) section of IAM in the AMZ console. This is *only* available when logging in using AWS account's *root* credentials.

- the public and private parts of the generated key should be stored in an entry in the [AWS Secrets Manager](https://us-east-1.console.aws.amazon.com/secretsmanager/home)

  - the name of the secret must match the value in the environment variable `SECRETS_MANAGER_CLOUDFRONT_KEY_PAIR_NAME` as defined in the `environment` section of [serverless.yml](./real-main/serverless.yml)
  - the `publicKey` and `privateKey` values in the secret must *not* contain the header and footer lines (ie the `----- BEGIN/END RSA PRIVATE KEY -----` lines)
  - the format of the secret should be

    ```json
    {
      "keyId": "<access key id>",
      "publicKey": "<cat public-key.pem | sed '1d;$d'>",
      "privateKey": "<cat private-key.pem | sed '1d;$d'>"
    }
    ```

## Internal stateful services

### DynamoDB Table Schema

  - Unless otherwise noted, all types are strings.
  - The table's primary key is (`partitionKey`, `sortKey`).
  - The item's `schemaVersion` is an integer attribute that is used for asynchronous data migrations.

| Table Partition Key `partitionKey` | Table Sort Key `sortKey` | Schema Version `schemaVersion` | Attributes | GSI-A1 Partition Key `gsiA1PartitionKey` | GSI-A1 Sort Key `gsiA1SortKey` | GSI-A2 Partition Key `gsiA2PartitionKey` | GSI-A2 Sort Key `gsiA2SortKey` | GSI-K1 Partition Key `gsiK1PartitionKey` | GSI-K1 Sort Key `gsiK1SortKey` | GSI-K2 Partition Key `gsiK2PartitionKey` | GSI-K2 Sort Key `gsiK2SortKey` | GSI-K3 Partition Key `gsiK3PartitionKey` | GSI-K3 Sort Key `gsiK3SortKey:Number` |
| - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| `user/{userId}` | `profile` | `5` | `userId`, `username`, `email`, `phoneNumber`, `fullName`, `bio`, `photoMediaId`, `privacyStatus`, `followerCount:Number`, `followedCount:Number`, `postCount:Number`, `lastManuallyReindexedAt`, `languageCode`, `themeCode`, `placeholderPhotoCode`, `signedUpAt`, `acceptedEULAVersion`, `postViewedByCount:Number`, `usernameLastValue`, `usernameLastChangedAt`, `followCountsHidden:Boolean`, `commentsDisabled:Boolean`, `likesDisabled:Boolean`, `sharingDisabled:Boolean`, `verificationHidden:Boolean` | `username/{username}` | `-` |
| `following/{followerUserId}/{followedUserId}` | `-`| `1` | `followedAt`, `followStatus`, `followerUserId`, `followedUserId`  | `follower/{followerUserId}` | `{followStatus}/{followedAt}` | `followed/{followedUserId}` | `{followStatus}/{followedAt}` |
| `followedFirstStory/{followerUserId}/{postedByUserId}` | `-`| `1` | `postId`, `postedAt`, `postedByUserId`, `expiresAt` | `followedFirstStory/{followerUserId}` | `{expiresAt}` |
| `block/{blockerUserId}/{blockedUserId}` | `-`| `0` | `blockerUserId`, `blockedUserId`, `blockedAt` | `block/{blockerUserId}` | `{blockedAt}` | `block/{blockedUserId}` | `{blockedAt}` |
| `post/{postId}` | `-` | `1` | `postId`, `postedAt`, `postedByUserId`, `postStatus`, `albumId`, `expiresAt`, `text`, `textTags:[{tag, userId}]`, `viewedByCount:Number`, `onymousLikeCount:Number`, `anonymousLikeCount:Number`, `flagCount:Number`, `commentCount:Number`, `commentsDisabled:Boolean`, `likesDisabled:Boolean`, `sharingDisabled:Boolean` | `post/{postedByUserId}` | `{postStatus}/{expiresAt}` | `post/{postedByUserId}` | `{postStatus}/{postedAt}` | `post/{expiresAtDate}` | `{expiresAtTime}` |  `post/{albumId}` | `{postStatus}/{postedAt}` |
| `flag/{flaggerUserId}/{postId}` | `-`| `1` | `flaggerUserId`, `postId`, `flaggedAt` | `flag/{flaggerUserId}` | `{flaggedAt}` | `flag/{postId}` | `{flaggedAt}` |
| `media/{mediaId}` | `-` | `0` | `postId`, `postedAt`, `userId`, `mediaId`, `mediaStatus`, `mediaType`, `isVerified:Boolean`, `takenInReal:Boolean`, `originalFormat`, `width:Number`, `height:Number` | `media/{postId}` | `{mediaStatus}` | `media/{userId}` | `{mediaType}/{mediaStatus}/{postedAt}` |
| `comment/{commentId}` | `-` | `0` | `commentId`, `postId`, `userId`, `commentedAt`, `text`, `textTags:[{tag, userId}]` | `comment/{postId}` | `{commentedAt}` | `comment/{userId}` | `{commentedAt}` |
| `feed/{userId}/{postId}` | `-` | `2` | `userId`, `postId`, `postedAt`, `postedByUserId`, | `feed/{userId}` | `{postedAt}` | | | | | `feed/{userId}/{postedByUserId}` | `{postedAt}` |
| `like/{likedByUserId}/{postId}` | `-` | `1` | `likedByUserId`, `likeStatus`, `likedAt`, `postId` | `like/{likedByUserId}` | `{likeStatus}/{likedAt}` | `like/{postId}` | `{likeStatus}/{likedAt}` | | | `like/{postedByUserId}` | `{likedByUserId}` |
| `trending/{itemId}` | `-` | `0` | `pendingViewCount:Number` | `trending/{itemType}` | `{lastIndexedAt}` | | | | | | | `trending/{itemType}` | `{score:Number}` |
| `postView/{postId}/{viewedByUserId}` | `-` | `0` | `postId`, `postedByUserId`, `viewedByUserId`, `viewCount:Number`, `firstViewedAt`, `lastViewedAt` | `postView/{postId}` | `{lastViewedAt}` |
| `album/{albumId}` | `-` | `0` | `albumId`, `ownedByUserId`, `name`, `description`, `createdAt`, `postCount:Number`, `postsLastUpdatedAt` | `album/{userId}` | `{createdAt}` |

Note that:

 - `userId` is both the cognito identity pool id for the user, and the cognito user pool 'username' (which isn't really a username at all)
 - `username` is a human-readable string of their choosing
 - other attributes that end with `Id` (ex: `postId`) are client-side-generated random uuids
 - attributes that end with `At` are  (ex: `followedAt`) are of type [AWSDateTime](https://docs.aws.amazon.com/appsync/latest/devguide/scalars.html#appsync-defined-scalars), ie an ISO8601 datetime string, with timezone information that is always just 'Z'
 - `expiresAtDate` is of type [AWSDate](https://docs.aws.amazon.com/appsync/latest/devguide/scalars.html#appsync-defined-scalars) and `expiresAtTime` is of type [AWSTime](https://docs.aws.amazon.com/appsync/latest/devguide/scalars.html#appsync-defined-scalars). Neither have timezone information.
 - keys that depend on optional attributes (ex: for posts, the GSI-A1 and GSI-K1 keys depend on `expiresAt`) will not be set if the optional attribute is not present
 - `textTags` is a list of maps, each map having two keys `tag` and `userId` both with string values

#### Global Secondary Indexes

- GSI-A1: (`gsiA1PartitionKey`, `gsiA1SortKey`) with keys and all attributes.
- GSI-A2: (`gsiA2PartitionKey`, `gsiA2SortKey`) with keys and all attributes.
- GSI-K1: (`gsiK1PartitionKey`, `gsiK1SortKey`) with keys only.
- GSI-K2: (`gsiK2PartitionKey`, `gsiK2SortKey`) with keys only.

#### Data Migrations

The order of operations to implement a data migration is:

  - deploy code that can read from both old `schemaVersion` and new `schemaVersion`, and uses new `schemaVersion` when adding items
  - run data migration transforming all items with old `schemaVersion` to new `schemaVersion`
  - deploy code that only reads and writes new `schemaVersion`

### S3 Object Paths

The following objects are stored with the given path structures:

- Post media objects: `{userId}/post/{postId}/media/{mediaId}/***.jpg`.
- Profile photo: `{userId}/profile-photo/{photoMediaId}/***.jpg`
