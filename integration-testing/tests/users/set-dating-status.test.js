const fs = require('fs')
const moment = require('moment')
const path = require('path')
const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito')
const {mutations, queries} = require('../../schema')

let anonClient
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
afterEach(async () => {
  if (anonClient) await anonClient.mutate({mutation: mutations.deleteUser})
  anonClient = null
})

// test('Set and read properties(currentLocation, matchAgeRange, matchGenders, matchLocationRadius)', async () => {
//   const {client: ourClient, userId} = await loginCache.getCleanLogin()
//   const {client: theirClient} = await loginCache.getCleanLogin()

//   // set up another user in cognito, leave them as public
//   const currentLocation = {latitude: 50.01, longitude: 50.01, accuracy: 50}
//   const matchAgeRange = {min: 20, max: 50}
//   const matchGenders = ['MALE', 'FEMALE']
//   const matchLocationRadius = 20

//   // Set match genders and location radius
//   await ourClient.mutate({
//     mutation: mutations.setUserDetails,
//     variables: {
//       matchGenders: matchGenders,
//       matchLocationRadius: matchLocationRadius,
//     },
//   })

//   // Set user age range
//   await ourClient.mutate({
//     mutation: mutations.setUserAgeRange,
//     variables: {
//       min: matchAgeRange.min,
//       max: matchAgeRange.max,
//     },
//   })

//   // Set user current location
//   await ourClient.mutate({
//     mutation: mutations.setUserCurrentLocation,
//     variables: {
//       latitude: currentLocation.latitude,
//       longitude: currentLocation.longitude,
//       accuracy: currentLocation.accuracy,
//     },
//   })

//   await ourClient.query({query: queries.self}).then(({data: {self: user}}) => {
//     expect(user.userId).toBe(userId)
//     expect(JSON.stringify(user.matchGenders)).toBe(JSON.stringify(matchGenders))
//     expect(user.matchLocationRadius).toBe(matchLocationRadius)
//     expect(user.matchAgeRange.min).toBe(matchAgeRange.min)
//     expect(user.matchAgeRange.max).toBe(matchAgeRange.max)
//     expect(user.currentLocation.latitude).toBe(currentLocation.latitude)
//     expect(user.currentLocation.longitude).toBe(currentLocation.longitude)
//     expect(user.currentLocation.accuracy).toBe(currentLocation.accuracy)
//   })

//   // check another user can't see values
//   await theirClient.query({query: queries.user, variables: {userId}}).then(({data: {user}}) => {
//     expect(user.userId).toBe(userId)
//     expect(user.matchGenders).toBeNull()
//     expect(user.matchLocationRadius).toBeNull()
//     expect(user.currentLocation).toBeNull()
//     expect(user.matchAgeRange).toBeNull()
//   })

//   // update current location without accuracy, process and check if accuracy is null
//   await ourClient.mutate({
//     mutation: mutations.setUserCurrentLocation,
//     variables: {
//       latitude: currentLocation.latitude,
//       longitude: currentLocation.longitude,
//     },
//   })

//   await ourClient.query({query: queries.user, variables: {userId}}).then(({data: {user}}) => {
//     expect(user.userId).toBe(userId)
//     expect(user.currentLocation.accuracy).toBeNull()
//   })
// })

test('Validate user dating status permission', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  // Validate match location radius
  await expect(
    ourClient.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {
        status: true,
      },
    }),
  ).rejects.toThrow(/ClientError: Some of required user fields are not set/)
})
