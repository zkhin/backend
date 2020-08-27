const cognito = require('../utils/cognito')
const {mutations} = require('../schema')

const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(2)

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Report views of some screens', async () => {
  const {client} = await loginCache.getCleanLogin()

  // verify reporting no screens is an error
  await expect(client.mutate({mutation: mutations.reportScreenViews, variables: {screens: []}})).rejects.toThrow(
    /ClientError: A minimum of 1 screen /,
  )

  // verify we can report one screen
  await client
    .mutate({mutation: mutations.reportScreenViews, variables: {screens: ['arbitrary']}})
    .then(({data: {reportScreenViews}}) => expect(reportScreenViews).toBe(true))

  // verify we can report three screens, including duplicates are ok
  await client
    .mutate({mutation: mutations.reportScreenViews, variables: {screens: ['a1', 's2', 'a1']}})
    .then(({data: {reportScreenViews}}) => expect(reportScreenViews).toBe(true))

  // verify reporting over 100 screens is an error
  await expect(
    client.mutate({mutation: mutations.reportScreenViews, variables: {screens: Array(101).fill('arbitrary')}}),
  ).rejects.toThrow(/ClientError: A max of 100 screens /)
})
