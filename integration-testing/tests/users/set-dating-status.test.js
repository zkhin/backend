const fs = require('fs')
const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const {mutations, queries} = require('../../schema')

const grantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(1)

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())
afterEach(async () => {})

test('Validate user dating status permission', async () => {
  const {client: ourClient, userId} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  // Check if the new user's datingStatus is DISABLED
  await ourClient.query({query: queries.user, variables: {userId}}).then(({data: {user}}) => {
    expect(user.userId).toBe(userId)
    expect(user.datingStatus).toBe('DISABLED')
  })

  // Validate user dating status permission
  await expect(
    ourClient.mutate({mutation: mutations.setUserDatingStatus, variables: {status: 'ENABLED'}}),
  ).rejects.toThrow(/ClientError: `fullName` is required field/)

  // Set fullName
  await ourClient.mutate({mutation: mutations.setUserDetails, variables: {fullName: 'Hunter S'}})
  await expect(
    ourClient.mutate({mutation: mutations.setUserDatingStatus, variables: {status: 'ENABLED'}}),
  ).rejects.toThrow(/ClientError: `photoPostId` is required field/)

  // Set photoPostId
  const postId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId, imageData: grantDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(postId))
  await ourClient
    .mutate({mutation: mutations.setUserDetails, variables: {photoPostId: postId}})
    .then(({data: {setUserDetails: user}}) => expect(user.photo.url).toBeTruthy())

  await expect(
    ourClient.mutate({mutation: mutations.setUserDatingStatus, variables: {status: 'ENABLED'}}),
  ).rejects.toThrow(/ClientError: `gender` is required field/)

  // Set gender
  await ourClient.mutate({mutation: mutations.setUserDetails, variables: {gender: 'MALE'}})
  await expect(
    ourClient.mutate({mutation: mutations.setUserDatingStatus, variables: {status: 'ENABLED'}}),
  ).rejects.toThrow(/ClientError: `currentLocation` is required field/)

  // Set currentLocation
  await ourClient.mutate({
    mutation: mutations.setUserCurrentLocation,
    variables: {
      latitude: 50.01,
      longitude: 50.01,
      accuracy: 20,
    },
  })
  await expect(
    ourClient.mutate({mutation: mutations.setUserDatingStatus, variables: {status: 'ENABLED'}}),
  ).rejects.toThrow(/ClientError: `matchGenders` is required field/)

  // Set matchGenders
  await ourClient.mutate({
    mutation: mutations.setUserDetails,
    variables: {
      matchGenders: ['MALE', 'FEMALE'],
    },
  })
  await expect(
    ourClient.mutate({mutation: mutations.setUserDatingStatus, variables: {status: 'ENABLED'}}),
  ).rejects.toThrow(/ClientError: `matchAgeRange` is required field/)

  // Set matchAgeRange
  await ourClient.mutate({
    mutation: mutations.setUserAgeRange,
    variables: {
      min: 20,
      max: 50,
    },
  })
  await expect(
    ourClient.mutate({mutation: mutations.setUserDatingStatus, variables: {status: 'ENABLED'}}),
  ).rejects.toThrow(/ClientError: `matchLocationRadius` is required field/)

  // Set matchLocationRadius
  await ourClient.mutate({
    mutation: mutations.setUserDetails,
    variables: {
      matchLocationRadius: 20,
    },
  })

  await ourClient.query({query: queries.user, variables: {userId}}).then(({data: {user}}) => {
    expect(user.userId).toBe(userId)
    expect(user.datingStatus).toBe('DISABLED')
  })
  // All required fields are fulfilled and check if datingStatus is ENABLED
  await ourClient
    .mutate({mutation: mutations.setUserDatingStatus, variables: {status: 'ENABLED'}})
    .then(({data: {setUserDatingStatus: user}}) => {
      expect(user.datingStatus).toBe('ENABLED')
    })

  // check another user can't see datingStatus value
  await theirClient.query({query: queries.user, variables: {userId}}).then(({data: {user}}) => {
    expect(user.userId).toBe(userId)
    expect(user.datingStatus).toBeNull()
  })

  // datingStatus can be set to DISABLED
  await ourClient
    .mutate({mutation: mutations.setUserDatingStatus, variables: {status: 'DISABLED'}})
    .then(({data: {setUserDatingStatus: user}}) => {
      expect(user.datingStatus).toBe('DISABLED')
    })

  // check another user can't see datingStatus value
  await theirClient.query({query: queries.user, variables: {userId}}).then(({data: {user}}) => {
    expect(user.userId).toBe(userId)
    expect(user.datingStatus).toBeNull()
  })
})
