const uuidv4 = require('uuid/v4')

const cognito = require('../utils/cognito')
const {mutations} = require('../schema')

const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(2)

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Upload app store receipt data', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  // receipt is verified async so mutation returns `true` even when uploading invalid data
  await ourClient
    .mutate({mutation: mutations.addAppStoreReceipt, variables: {receiptData: uuidv4()}})
    .then(({data}) => expect(data.addAppStoreReceipt).toBe(true))
})
